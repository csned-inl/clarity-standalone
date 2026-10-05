"""Derive a zero-training affine-predicate policy from #NeuralRequirement."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

from sysml_parser import BinaryExpr, LiteralExpr, RefExpr, UnaryExpr
from shield import SpecShield, _flatten_and


def _affine(expr, inputs: set[str], constants: dict, subject: str):
    if isinstance(expr, LiteralExpr) and isinstance(expr.value, (int, float)):
        return {}, float(expr.value)
    if isinstance(expr, RefExpr):
        path = list(expr.path)
        if path and path[0] == subject:
            path = path[1:]
        if len(path) != 1:
            raise ValueError(f"non-scalar affine reference: {expr.path}")
        name = path[0]
        if name in inputs:
            return {name: 1.0}, 0.0
        if name in constants:
            return {}, float(constants[name])
        raise ValueError(f"unresolved affine reference: {name}")
    if isinstance(expr, UnaryExpr) and expr.op == "-":
        weights, bias = _affine(expr.operand, inputs, constants, subject)
        return {key: -value for key, value in weights.items()}, -bias
    if isinstance(expr, BinaryExpr) and expr.op in {"+", "-"}:
        left, lb = _affine(expr.left, inputs, constants, subject)
        right, rb = _affine(expr.right, inputs, constants, subject)
        sign = 1 if expr.op == "+" else -1
        result = dict(left)
        for key, value in right.items():
            result[key] = result.get(key, 0.0) + sign * value
        return {k: v for k, v in result.items() if v != 0.0}, lb + sign * rb
    if isinstance(expr, BinaryExpr) and expr.op == "*":
        left, lb = _affine(expr.left, inputs, constants, subject)
        right, rb = _affine(expr.right, inputs, constants, subject)
        if left and right:
            raise ValueError("nonlinear product in policy condition")
        if left:
            return {k: v * rb for k, v in left.items()}, lb * rb
        return {k: v * lb for k, v in right.items()}, rb * lb
    raise ValueError(f"not an affine expression: {expr!r}")


def _output_ref(expr, outputs: set[str], subject: str):
    if not isinstance(expr, RefExpr):
        return None
    path = list(expr.path)
    if path and path[0] == subject:
        path = path[1:]
    return path[0] if len(path) == 1 and path[0] in outputs else None


def _predicate(expr, inputs: set[str], outputs: set[str], constants: dict,
               subject: str):
    output = _output_ref(expr, outputs, subject)
    if output is not None:
        return {"kind": "output", "name": output}
    if isinstance(expr, LiteralExpr) and isinstance(expr.value, bool):
        return {"kind": "literal", "value": expr.value}
    if isinstance(expr, UnaryExpr) and expr.op == "not":
        return {"kind": "not", "child": _predicate(
            expr.operand, inputs, outputs, constants, subject)}
    if isinstance(expr, BinaryExpr):
        if expr.op in {"and", "or"}:
            return {"kind": expr.op,
                    "left": _predicate(expr.left, inputs, outputs, constants, subject),
                    "right": _predicate(expr.right, inputs, outputs, constants, subject)}
        if expr.op in {">", ">=", "<", "<="}:
            left, lb = _affine(expr.left, inputs, constants, subject)
            right, rb = _affine(expr.right, inputs, constants, subject)
            weights = dict(left)
            for key, value in right.items():
                weights[key] = weights.get(key, 0.0) - value
            return {"kind": "affine_comparison", "operator": expr.op,
                    "weights": {k: v for k, v in weights.items() if v != 0.0},
                    "bias": lb - rb}
    raise ValueError(f"policy condition is not an affine predicate: {expr!r}")


def fit(model_path: str | Path):
    """Read SysML and return serializable predicates for every policy output."""
    model_path = Path(model_path).resolve()
    shield = SpecShield(str(model_path))
    inputs = set(shield.in_params)
    outputs = set(shield.out_params)
    rules = {}
    for clause in _flatten_and(shield.req_ast):
        if not isinstance(clause, BinaryExpr) or clause.op != "==":
            continue
        for output_expr, condition in ((clause.left, clause.right),
                                       (clause.right, clause.left)):
            name = _output_ref(output_expr, outputs, shield.subject_var)
            if name is None or name in rules:
                continue
            rules[name] = _predicate(condition, inputs, outputs,
                                     shield.unchanging, shield.subject_var)
            break
    missing = outputs - set(rules)
    if missing:
        raise ValueError(f"no affine rule for outputs: {sorted(missing)}")
    return {"kind": "sysml_derived_affine_predicate_policy",
            "source_model": str(model_path.relative_to(Path(__file__).resolve().parent)),
            "source_model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "input_names": sorted(inputs),
            "output_names": list(shield.out_params),
            "rules": rules,
            "dead_actions": sorted(shield.dead_actions)}


def _eval(tree: dict, observation: dict, output: callable):
    kind = tree["kind"]
    if kind == "literal":
        return tree["value"]
    if kind == "output":
        return output(tree["name"])
    if kind == "not":
        return not _eval(tree["child"], observation, output)
    if kind == "and":
        return _eval(tree["left"], observation, output) and _eval(
            tree["right"], observation, output)
    if kind == "or":
        return _eval(tree["left"], observation, output) or _eval(
            tree["right"], observation, output)
    if kind == "affine_comparison":
        value = tree["bias"] + sum(
            weight * float(observation[name])
            for name, weight in tree["weights"].items())
        return {">": lambda: value > 0, ">=": lambda: value >= 0,
                "<": lambda: value < 0, "<=": lambda: value <= 0}[
                    tree["operator"]]()
    raise ValueError(f"unknown predicate kind: {kind}")


def action(policy: dict, observation: dict) -> int:
    values = {}
    visiting = set()

    def output(name):
        if name not in values:
            if name in visiting:
                raise ValueError(f"cyclic output dependency: {name}")
            visiting.add(name)
            values[name] = bool(_eval(policy["rules"][name], observation, output))
            visiting.remove(name)
        return values[name]

    result = 0
    for bit, name in enumerate(policy["output_names"]):
        if output(name):
            result |= 1 << bit
    return result


def save(policy: dict, path: str | Path):
    Path(path).write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n")


def evaluate(model_path: str | Path, policy: dict, *, episodes: int,
             seed: int, max_steps: int, dt: float | None = None) -> dict:
    """Evaluate the fitted rule and its SysML-derived shield in the twin."""
    from env import SysMLEnv

    if episodes <= 0:
        raise ValueError("evaluation episodes must be positive")
    shield = SpecShield(str(model_path))
    env = SysMLEnv(str(model_path), dt=dt, max_steps=max_steps, phase=2,
                   rng_seed=seed)
    n_success = n_safety = n_errors = n_overrides = n_steps = n_disagreements = 0
    error_messages = []
    failed_requirements = {}
    try:
        for _episode in range(episodes):
            try:
                initial = env.reset_with_result()
                if initial.error or initial.errors:
                    raise RuntimeError(initial.error or str(initial.errors))
                if initial.violations:
                    n_safety += 1
                    for name in initial.violations:
                        failed_requirements[name] = failed_requirements.get(name, 0) + 1
                    continue
                if initial.outcome != 'decision':
                    raise RuntimeError(f'reset ended with {initial.outcome}')
                done = False
                last_reward = 0.0
                episode_violated = False
                while not done:
                    raw = dict(env._twin._model_inputs)
                    proposed = action(policy, raw)
                    n_disagreements += int(proposed != shield._requirement_action(raw))
                    executed = shield(proposed, raw)
                    n_overrides += int(executed != proposed)
                    _obs, last_reward, done, _info = env.step(executed)
                    n_steps += 1
                    statuses = _info['statuses']
                    if _info['outcome'] == 'ERROR':
                        raise RuntimeError(_info['error'] or str(_info['evaluation_errors']))
                    for name, row in statuses.items():
                        if not row["status"]:
                            failed_requirements[name] = failed_requirements.get(name, 0) + 1
                            episode_violated = True
                n_success += int(last_reward > 0)
                n_safety += int(episode_violated)
            except Exception as exc:
                n_errors += 1
                error_messages.append(f"{type(exc).__name__}: {exc}")
                break
    finally:
        env.close()
    return {
        "episodes_requested": episodes,
        "safety_violation_episodes": n_safety,
        "evaluation_errors": n_errors,
        "error_messages": error_messages,
        "failed_requirement_checks": failed_requirements,
        "successes": n_success,
        "task_error_rate": (episodes - n_success) / episodes,
        "total_steps": n_steps,
        "shield_overrides": n_overrides,
        "shield_override_rate": n_overrides / max(n_steps, 1),
        "pointwise_rule_disagreements": n_disagreements,
    }
