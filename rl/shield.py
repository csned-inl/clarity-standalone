"""
Specification-derived safety shield for SysML neural controllers.

Extracts from the #NeuralRequirement:
  - Full AST (prohibitions + obligations)
  - Output-only clauses → structurally dead actions
  - All clause structure for neural compilation

Compiles the parsed expression once into ordinary Python predicates.
Runtime comparisons use the original observation values and source operators.
"""

import ast
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sysml-models"))

from sysml_parser import (
    SysMLParser, ExpressionParser, BinaryExpr, RefExpr, LiteralExpr,
    UnaryExpr, TernaryExpr, Expr,
)


# ---------------------------------------------------------------------------
# AST evaluator
# ---------------------------------------------------------------------------

class NoValidActionError(RuntimeError):
    pass


def _compile_predicate(expr, inputs, constants, subject_var):
    """Compile only recognized parser nodes; never execute source model text."""
    arithmetic = {'+': ast.Add, '-': ast.Sub, '*': ast.Mult, '/': ast.Div}
    comparisons = {'==': ast.Eq, '>=': ast.GtE, '<=': ast.LtE,
                   '>': ast.Gt, '<': ast.Lt}

    def build(node):
        if isinstance(node, LiteralExpr):
            return ast.Constant(node.value)
        if isinstance(node, RefExpr):
            path = list(node.path)
            if path and path[0] == subject_var:
                path = path[1:]
            key = '.'.join(path)
            if key in inputs:
                return ast.Subscript(ast.Name('obs', ast.Load()), ast.Constant(key), ast.Load())
            if key in constants and type(constants[key]) in (bool, int, float):
                return ast.Constant(constants[key])
            raise ValueError(f'undefined requirement reference: {key}')
        if isinstance(node, UnaryExpr):
            operators = {'not': ast.Not, '-': ast.USub}
            if node.op not in operators:
                raise ValueError(f'unsupported unary operator: {node.op}')
            return ast.UnaryOp(operators[node.op](), build(node.operand))
        if isinstance(node, TernaryExpr):
            return ast.IfExp(build(node.condition), build(node.true_expr), build(node.false_expr))
        if isinstance(node, BinaryExpr):
            left, right = build(node.left), build(node.right)
            if node.op in arithmetic:
                return ast.BinOp(left, arithmetic[node.op](), right)
            if node.op in comparisons:
                return ast.Compare(left, [comparisons[node.op]()], [right])
            if node.op in ('and', 'or'):
                return ast.BoolOp(ast.And() if node.op == 'and' else ast.Or(), [left, right])
            if node.op == 'implies':
                return ast.BoolOp(ast.Or(), [ast.UnaryOp(ast.Not(), left), right])
        raise ValueError(f'unsupported requirement node: {node!r}')

    expression = ast.Expression(ast.Lambda(
        ast.arguments(posonlyargs=[], args=[ast.arg(arg='obs')],
                      kwonlyargs=[], kw_defaults=[], defaults=[]), build(expr)))
    function = eval(compile(ast.fix_missing_locations(expression), '<SysML shield>', 'eval'),
                    {'__builtins__': {}})

    def predicate(obs):
        result = function(obs)
        if type(result) is not bool:
            raise ValueError('NeuralRequirement did not evaluate to Boolean')
        return result
    return predicate

def _evaluate(expr, values: dict, subject_var: str = ""):
    if isinstance(expr, LiteralExpr):
        return expr.value
    if isinstance(expr, RefExpr):
        path = list(expr.path)
        if path and path[0] == subject_var:
            path = path[1:]
        key = ".".join(path)
        if key in values:
            return values[key]
        if len(path) == 1 and path[0] in values:
            return values[path[0]]
        raise KeyError(f"Unknown ref: {'.'.join(expr.path)}")
    if isinstance(expr, BinaryExpr):
        if expr.op == 'and':
            return _evaluate(expr.left, values, subject_var) and _evaluate(expr.right, values, subject_var)
        if expr.op == 'or':
            return _evaluate(expr.left, values, subject_var) or _evaluate(expr.right, values, subject_var)
        if expr.op == "implies":
            left = _evaluate(expr.left, values, subject_var)
            return True if not left else _evaluate(expr.right, values, subject_var)
        left = _evaluate(expr.left, values, subject_var)
        right = _evaluate(expr.right, values, subject_var)
        ops = {
            "+": lambda a, b: a + b, "-": lambda a, b: a - b,
            "*": lambda a, b: a * b, "/": lambda a, b: a / b,
            "==": lambda a, b: a == b, ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b, ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            "and": lambda a, b: a and b, "or": lambda a, b: a or b,
        }
        return ops[expr.op](left, right)
    if isinstance(expr, UnaryExpr):
        val = _evaluate(expr.operand, values, subject_var)
        if expr.op == "not":
            return not val
        if expr.op == "-":
            return -val
    if isinstance(expr, TernaryExpr):
        cond = _evaluate(expr.condition, values, subject_var)
        return _evaluate(expr.true_expr if cond else expr.false_expr,
                         values, subject_var)
    raise ValueError(f'unsupported requirement node: {expr!r}')


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------

def _collect_refs(expr) -> set:
    refs = set()
    if isinstance(expr, RefExpr):
        refs.add(expr.path[-1])
    elif isinstance(expr, BinaryExpr):
        refs.update(_collect_refs(expr.left))
        refs.update(_collect_refs(expr.right))
    elif isinstance(expr, UnaryExpr):
        refs.update(_collect_refs(expr.operand))
    elif isinstance(expr, TernaryExpr):
        refs.update(_collect_refs(expr.condition))
        refs.update(_collect_refs(expr.true_expr))
        refs.update(_collect_refs(expr.false_expr))
    return refs


def _flatten_and(expr) -> list:
    if isinstance(expr, BinaryExpr) and expr.op == 'and':
        return _flatten_and(expr.left) + _flatten_and(expr.right)
    return [expr]


# ---------------------------------------------------------------------------
# SpecShield — extraction only, used at construction time
# ---------------------------------------------------------------------------

class SpecShield:
    """Extracts shield data from SysML specification.

    After construction, provides:
      - req_ast: full requirement AST
      - in_params, out_params: neural interface
      - unchanging: controller constants
      - action_map: action_id → actuator dict
      - dead_actions: structurally invalid actions
      - prohibition_clauses: output-only clauses

    Callable at runtime: shield(action_id, obs_dict) → action_id
    """

    def __init__(self, model_path: str):
        parser = SysMLParser(model_path)
        parser.parse()

        ctrl_fqn = parser.controller_part
        ctrl_inst = parser.part_instances[ctrl_fqn]
        ctrl_def = parser.part_defs[ctrl_inst.part_type]

        neural_def = None
        for ad in ctrl_def.action_defs:
            if "Neural" in ad.metadata:
                neural_def = ad
                break

        self.in_params = [p.name for p in neural_def.in_params]
        self.out_params = [p.name for p in neural_def.out_params]
        in_set = set(self.in_params)
        out_set = set(self.out_params)

        self.req_ast = None
        self.subject_var = ""
        for req_name, sv, _st, req_expr, req_meta in ctrl_def.requirements:
            if "NeuralRequirement" in req_meta:
                self.req_ast = ExpressionParser(req_expr).parse()
                self.subject_var = sv
                break

        ctrl_prefix = ctrl_fqn + "::"
        neural_names = in_set | out_set
        self.unchanging = {}
        for p in parser.parameters:
            if p.qualified_name.startswith(ctrl_prefix) and p.name not in neural_names:
                self.unchanging[p.name] = p.value

        # Pick up controller constants not tagged #ScenarioInput
        # (e.g., toleranceMl) that appear in the requirement AST
        if self.req_ast:
            req_refs = _collect_refs(self.req_ast)
            req_refs.discard(self.subject_var)
            missing = req_refs - in_set - out_set - set(self.unchanging.keys())
            if missing:
                from simulator import SimulationEngine, BindRef
                eng = SimulationEngine(parser)
                eng.initialize()
                for key, val in eng.state.items():
                    if isinstance(val, BindRef):
                        continue
                    if key.startswith(ctrl_prefix):
                        name = key[len(ctrl_prefix):]
                        if name in missing:
                            self.unchanging[name] = val
                            missing.discard(name)
                if missing:
                    raise ValueError(f"unresolved requirement references: {missing}")

        if self.req_ast is None:
            raise ValueError("missing NeuralRequirement")
        self._required_inputs = in_set & _collect_refs(self.req_ast)
        n_out = len(self.out_params)
        self.action_map = {}
        for action_id in range(2 ** n_out):
            actuators = {}
            for bit, name in enumerate(self.out_params):
                actuators[name] = bool(action_id & (1 << bit))
            self.action_map[action_id] = actuators

        # Dead actions from output-only clauses
        self.dead_actions = set()
        self.prohibition_clauses = []
        if self.req_ast:
            clauses = _flatten_and(self.req_ast)
            for clause in clauses:
                refs = _collect_refs(clause)
                refs = {r for r in refs if r != self.subject_var}
                if refs and refs.issubset(out_set | set(self.unchanging.keys())):
                    self.prohibition_clauses.append(clause)

        for action_id, actuators in self.action_map.items():
            values = {**self.unchanging, **actuators}
            for clause in self.prohibition_clauses:
                if not _evaluate(clause, values, self.subject_var):
                    self.dead_actions.add(action_id)
                    break

        self._predicates = {
            a: _compile_predicate(self.req_ast, self.in_params,
                                  {**self.unchanging, **outputs}, self.subject_var)
            for a, outputs in self.action_map.items()
        }
        print(f"  [SpecShield] Compiled Python helper from {model_path}")
        print(f"  [SpecShield] dead_actions={sorted(self.dead_actions)}, "
              f"n_valid={2**n_out - len(self.dead_actions)}")

    def _validate_observation(self, obs_dict):
        for name in self._required_inputs:
            value = obs_dict[name]
            if type(value) not in (bool, int, float) or not math.isfinite(value):
                raise ValueError(f"invalid Neural input {name}: {value!r}")

    def is_valid(self, action_id, obs_dict):
        self._validate_observation(obs_dict)
        if action_id not in self.action_map:
            raise ValueError(f"unknown action: {action_id}")
        return action_id not in self.dead_actions and self._predicates[action_id](obs_dict)

    def valid_actions(self, obs_dict):
        self._validate_observation(obs_dict)
        return tuple(a for a in self.action_map if a not in self.dead_actions
                     and self._predicates[a](obs_dict))

    def _requirement_action(self, obs_dict):
        valid = self.valid_actions(obs_dict)
        if not valid:
            raise NoValidActionError("no action satisfies the source NeuralRequirement")
        return min(valid, key=lambda a: (a.bit_count(), a))

    def select(self, proposed_action, obs_dict, policy_probs=None):
        if self.is_valid(proposed_action, obs_dict):
            return proposed_action, False
        valid = self.valid_actions(obs_dict)
        if not valid:
            raise NoValidActionError("no action satisfies the source NeuralRequirement")
        if len(valid) == 1:
            return valid[0], True
        if policy_probs is not None:
            return max(valid, key=lambda a: (float(policy_probs[a]), -a)), True
        return min(valid, key=lambda a: (a.bit_count(), a)), True

    def __call__(self, proposed_action, obs_dict):
        return self.select(proposed_action, obs_dict)[0]
