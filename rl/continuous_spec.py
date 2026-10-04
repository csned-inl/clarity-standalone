"""Type-driven continuous-action contract extraction for CLARITY SysML.

The first supported contract is deliberately narrow: one ``Real`` neural
output constrained by a top-level equality that isolates that output.  This is
the exact-feedback shape used by the rotary inverted-pendulum source model.
Unsupported shapes fail closed instead of being approximated.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
import sys
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sysml-models"))

from sysml_parser import (  # noqa: E402
    BinaryExpr,
    ExpressionParser,
    LiteralExpr,
    RefExpr,
    SysMLParser,
    TernaryExpr,
    UnaryExpr,
)


class UnsupportedContinuousContract(ValueError):
    """The source contract is not in the sound, implemented subset."""


def _walk_refs(expr) -> list[RefExpr]:
    if isinstance(expr, RefExpr):
        return [expr]
    if isinstance(expr, BinaryExpr):
        return _walk_refs(expr.left) + _walk_refs(expr.right)
    if isinstance(expr, UnaryExpr):
        return _walk_refs(expr.operand)
    if isinstance(expr, TernaryExpr):
        return (_walk_refs(expr.condition) + _walk_refs(expr.true_expr)
                + _walk_refs(expr.false_expr))
    return []


def _strip_subject(path: list[str], subject: str) -> list[str]:
    return path[1:] if path and path[0] == subject else path


def _is_output_ref(expr, subject: str, output: str) -> bool:
    return (isinstance(expr, RefExpr)
            and _strip_subject(list(expr.path), subject) == [output])


def _eval_numeric(expr, values: dict[str, Any], subject: str):
    if isinstance(expr, LiteralExpr):
        return expr.value
    if isinstance(expr, RefExpr):
        path = _strip_subject(list(expr.path), subject)
        if len(path) != 1 or path[0] not in values:
            raise KeyError(f"unknown continuous-contract reference: {'.'.join(expr.path)}")
        return values[path[0]]
    if isinstance(expr, UnaryExpr):
        value = _eval_numeric(expr.operand, values, subject)
        if expr.op == "-":
            return -value
        if expr.op == "not":
            return not value
        raise UnsupportedContinuousContract(f"unsupported unary operator: {expr.op}")
    if isinstance(expr, TernaryExpr):
        condition = _eval_numeric(expr.condition, values, subject)
        branch = expr.true_expr if condition else expr.false_expr
        return _eval_numeric(branch, values, subject)
    if isinstance(expr, BinaryExpr):
        if expr.op == "and":
            return (_eval_numeric(expr.left, values, subject)
                    and _eval_numeric(expr.right, values, subject))
        if expr.op == "or":
            return (_eval_numeric(expr.left, values, subject)
                    or _eval_numeric(expr.right, values, subject))
        if expr.op == "implies":
            left = _eval_numeric(expr.left, values, subject)
            return ((not left)
                    or _eval_numeric(expr.right, values, subject))
        left = _eval_numeric(expr.left, values, subject)
        right = _eval_numeric(expr.right, values, subject)
        operators = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b,
            "==": lambda a, b: a == b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
        }
        if expr.op not in operators:
            raise UnsupportedContinuousContract(
                f"unsupported binary operator: {expr.op}")
        return operators[expr.op](left, right)
    raise UnsupportedContinuousContract(
        f"unsupported continuous-contract node: {expr!r}")


@dataclass(frozen=True)
class ContinuousInterface:
    input_names: tuple[str, ...]
    input_types: tuple[str, ...]
    output_name: str
    output_type: str
    required_input_names: tuple[str, ...]


class ExactContinuousShield:
    """Extract and enforce one exact real-valued neural-output relation.

    This object does not claim that an equality contract leaves the learned
    controller autonomous.  ``select`` always returns the source-required
    action.  The proposal is retained only to measure approximation error.
    """

    def __init__(self, model_path: str, *, comparison_abs_tol: float = 1e-6):
        self.model_path = model_path
        self.comparison_abs_tol = comparison_abs_tol
        parser = SysMLParser(model_path)
        parser.parse()

        controller_fqn = parser.controller_part
        if not controller_fqn:
            raise UnsupportedContinuousContract("missing controller part")
        controller_instance = parser.part_instances[controller_fqn]
        controller_def = parser.part_defs[controller_instance.part_type]

        neural_defs = [definition for definition in controller_def.action_defs
                       if "Neural" in definition.metadata]
        if len(neural_defs) != 1:
            raise UnsupportedContinuousContract(
                f"expected exactly one #Neural action, found {len(neural_defs)}")
        neural = neural_defs[0]
        if len(neural.out_params) != 1:
            raise UnsupportedContinuousContract(
                "exact continuous path requires exactly one output")
        output = neural.out_params[0]
        if output.type_name != "Real":
            raise UnsupportedContinuousContract(
                f"continuous output must be Real, got {output.type_name!r}")

        requirements = [row for row in controller_def.requirements
                        if "NeuralRequirement" in row[4]]
        if len(requirements) != 1:
            raise UnsupportedContinuousContract(
                f"expected exactly one #NeuralRequirement, found {len(requirements)}")
        _name, subject, _subject_type, requirement_text, _metadata = requirements[0]
        requirement = ExpressionParser(requirement_text).parse()
        if not isinstance(requirement, BinaryExpr) or requirement.op != "==":
            raise UnsupportedContinuousContract(
                "continuous fast path requires a top-level output equality")

        if _is_output_ref(requirement.left, subject, output.name):
            action_expr = requirement.right
        elif _is_output_ref(requirement.right, subject, output.name):
            action_expr = requirement.left
        else:
            raise UnsupportedContinuousContract(
                "equality must isolate the neural output on one side")
        if any(_is_output_ref(ref, subject, output.name)
               for ref in _walk_refs(action_expr)):
            raise UnsupportedContinuousContract(
                "action expression recursively references its output")

        input_names = tuple(param.name for param in neural.in_params)
        input_types = tuple(param.type_name for param in neural.in_params)
        neural_names = set(input_names) | {output.name}
        controller_prefix = controller_fqn + "::"
        constants = {
            parameter.name: parameter.value
            for parameter in parser.parameters
            if parameter.qualified_name.startswith(controller_prefix)
            and parameter.name not in neural_names
            and type(parameter.value) in (bool, int, float)
        }

        required = set()
        unresolved = set()
        for ref in _walk_refs(action_expr):
            path = _strip_subject(list(ref.path), subject)
            if len(path) != 1:
                unresolved.add(".".join(ref.path))
            elif path[0] in input_names:
                required.add(path[0])
            elif path[0] not in constants:
                unresolved.add(path[0])
        if unresolved:
            raise UnsupportedContinuousContract(
                f"unresolved action-expression references: {sorted(unresolved)}")

        self.parser = parser
        self.subject_var = subject
        self.action_expr = action_expr
        self.constants = constants
        self.interface = ContinuousInterface(
            input_names=input_names,
            input_types=input_types,
            output_name=output.name,
            output_type=output.type_name,
            required_input_names=tuple(name for name in input_names
                                       if name in required),
        )

    @property
    def in_params(self) -> list[str]:
        return list(self.interface.input_names)

    @property
    def out_params(self) -> list[str]:
        return [self.interface.output_name]

    def required_action(self, observation: dict[str, Any]) -> float:
        for name in self.interface.required_input_names:
            value = observation[name]
            if type(value) not in (bool, int, float):
                raise ValueError(f"invalid Neural input {name}: {value!r}")
            if not isinstance(value, bool) and not math.isfinite(float(value)):
                raise ValueError(f"non-finite Neural input {name}: {value!r}")
        value = _eval_numeric(
            self.action_expr, {**self.constants, **observation}, self.subject_var)
        if type(value) not in (int, float) or not math.isfinite(float(value)):
            raise ValueError(f"continuous requirement produced invalid action: {value!r}")
        return float(value)

    def select(self, proposed_action: float, observation: dict[str, Any]):
        required = self.required_action(observation)
        proposed = float(proposed_action)
        if not math.isfinite(proposed):
            overridden = True
            correction = math.inf
        else:
            overridden = not math.isclose(
                proposed, required, rel_tol=0.0,
                abs_tol=self.comparison_abs_tol)
            correction = abs(proposed - required)
        return required, overridden, correction

    def report(self) -> dict[str, Any]:
        return {
            "contract_kind": "exact_real_output_equality",
            "input_names": list(self.interface.input_names),
            "input_types": list(self.interface.input_types),
            "required_input_names": list(self.interface.required_input_names),
            "output_name": self.interface.output_name,
            "output_type": self.interface.output_type,
            "learned_policy_autonomous": False,
            "execution_rule": "source equality replaces nonmatching proposals",
        }
