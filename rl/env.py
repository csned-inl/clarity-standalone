"""
Gym-style environment wrapping the SysML SimulatorTwin.

All structure is derived from SysML extraction.  Environment construction is
static: it does not execute the process merely to discover normalization.
"""

import sys
import os
import math
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sysml-models"))

from sysml_parser import SysMLParser, BinaryExpr, RefExpr, LiteralExpr, UnaryExpr
from simulator_adapter import SimulatorTwin
from requirement_events import ResetResult, ResetUnavailable, summarize_events


class SysMLEnv:
    """RL environment derived from any SysML model with a #Neural action."""

    def __init__(self, model_path: str, dt: float | None = None,
                 max_steps: int = 1200, phase: int = 1,
                 rng_seed: int = None, *,
                 observation_scales: dict[str, float] | None = None):
        self._model_path = model_path
        self._twin = SimulatorTwin(model_path, dt=dt)
        self._max_steps = max_steps
        self.phase = phase
        self._step_count = 0
        self._rng = np.random.default_rng(rng_seed)

        parser = self._twin._parser

        self._out_params = []
        self._obs_keys = []
        for pdef in parser.part_defs.values():
            for ad in pdef.action_defs:
                if "Neural" in ad.metadata:
                    # A #Completion input is supplied by the execution engine
                    # to declare termination.  It is not information available
                    # to the controller before it chooses an action.
                    self._obs_keys = [
                        p.name for p in ad.in_params
                        if "Completion" not in p.metadata
                    ]
                    self._out_params = [
                        (p.name, p.type_name) for p in ad.out_params
                    ]
                    break
            if self._out_params:
                break

        n_out = len(self._out_params)
        self._action_map = {}
        for action_id in range(2 ** n_out):
            actuators = {}
            for bit, (name, _) in enumerate(self._out_params):
                actuators[name] = bool(action_id & (1 << bit))
            self._action_map[action_id] = actuators

        self.obs_dim = len(self._obs_keys)
        self.n_actions = len(self._action_map)
        self._scenario_inputs = _extract_scenario_bounds(parser)
        self._cross_constraints = _extract_cross_constraints(parser)
        self._obs_scale = self._compute_obs_scale(
            parser, observation_scales=observation_scales
        )

    def _compute_obs_scale(self, parser, *, observation_scales):
        """Compute a static global scale from declared model constants.

        The old implementation reset and advanced the simulator during the
        constructor.  That silently executed a control transition before an
        episode and made environment construction depend on a chosen action.
        A declared-constant scale is deterministic, side-effect free, and
        cannot leak a completion value into the policy observation.
        """
        if observation_scales is not None:
            unknown = set(observation_scales) - set(self._obs_keys)
            missing = set(self._obs_keys) - set(observation_scales)
            if unknown or missing:
                raise ValueError(
                    "observation scales must cover exactly the policy inputs; "
                    f"missing={sorted(missing)}, unknown={sorted(unknown)}"
                )
            scales = {}
            for key in self._obs_keys:
                value = observation_scales[key]
                if (type(value) not in (int, float)
                        or not math.isfinite(float(value))
                        or float(value) <= 0.0):
                    raise ValueError(
                        f"invalid observation scale for {key}: {value!r}"
                    )
                scales[key] = float(value)
            return scales

        candidates = [1.0]
        for parameter in parser.parameters:
            value = parameter.value
            if (type(value) in (int, float)
                    and math.isfinite(float(value))):
                candidates.append(abs(float(value)))
        for bounds in self._scenario_inputs.values():
            for name in ("default", "lower", "upper"):
                value = bounds[name]
                if (type(value) in (int, float)
                        and math.isfinite(float(value))):
                    candidates.append(abs(float(value)))
        scale = max(candidates)
        return {key: scale for key in self._obs_keys}

    def _sample_scenario(self):
        """Sample each ScenarioInput uniformly within its constraint bounds."""
        values = {}
        for qname, info in self._scenario_inputs.items():
            lo, hi = info["lower"], info["upper"]
            if lo == hi:
                values[qname] = lo
            elif isinstance(lo, int) and isinstance(hi, int):
                values[qname] = float(self._rng.integers(lo, hi + 1))
            else:
                values[qname] = self._rng.uniform(lo, hi)
        for greater_qname, lesser_qname in self._cross_constraints:
            greater = values.get(greater_qname, 0)
            lesser = values.get(lesser_qname, 0)
            if greater < lesser + 5:
                values[lesser_qname] = max(
                    greater - 5,
                    self._scenario_inputs[lesser_qname]["lower"],
                )
        for qname in self._scenario_inputs:
            if "OriginalLevel" in qname:
                for parameter in self._twin.parser.parameters:
                    key = parameter.qualified_name
                    if "currentLevelMl" in key:
                        for digit in "0123456789":
                            if digit in qname and digit in key:
                                values[key] = values[qname]
                                break
        return values

    def _state_to_obs(self, state: dict) -> np.ndarray:
        obs = []
        for key in self._obs_keys:
            value = state.get(key, 0.0)
            if isinstance(value, bool):
                obs.append(float(value))
            else:
                obs.append(float(value) / self._obs_scale[key])
        return np.array(obs, dtype=np.float32)

    def reset_with_result(self, seed: int = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._twin.prepare(self._sample_scenario())
        result = self._twin.start()
        statuses = summarize_events(result.events)
        outcome = result.outcome
        if result.error or any(row["errors"] for row in statuses.values()):
            outcome = "error"
        elif self.phase == 2 and any(
                row["status"] is False for row in statuses.values()):
            outcome = "violation"
        observation = (
            self._state_to_obs(result.state) if outcome == "decision" else None
        )
        self.reset_result = ResetResult(
            observation, outcome, result.events, result.error
        )
        self._episode_done = outcome != "decision"
        return self.reset_result

    def reset(self, seed: int = None) -> np.ndarray:
        result = self.reset_with_result(seed)
        if result.outcome != "decision":
            raise ResetUnavailable(result)
        return result.observation

    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]:
        if self._episode_done:
            raise RuntimeError("cannot act after terminal/error/reset failure")
        actuators = self._action_map[action]
        result = self._twin.advance(actuators)
        self._step_count += 1
        statuses = summarize_events(result.events)
        errors = {
            name: row["errors"] for name, row in statuses.items()
            if row["errors"]
        }
        if errors or result.error:
            reward, done, outcome = 0.0, True, "ERROR"
        elif self.phase == 2 and any(
                row["status"] is False for row in statuses.values()):
            reward, done, outcome = -1.0, True, "VIOLATION"
        elif result.outcome == "terminal":
            reward, done, outcome = 1.0, True, "SUCCESS"
        else:
            reward, done, outcome = -0.01, False, "RUNNING"
        truncated = self._step_count >= self._max_steps and not done
        if truncated:
            reward, done, outcome = 0.0, True, "TRUNCATED"
        self._episode_done = done
        info = {
            "step": self._step_count,
            "state": result.state,
            "statuses": statuses,
            "requirement_events": result.events,
            "error": result.error,
            "evaluation_errors": errors,
            "outcome": outcome,
            "truncated": truncated,
        }
        observation = (
            None if result.state is None else self._state_to_obs(result.state)
        )
        return observation, reward, done, info

    def close(self):
        self._twin._stop()


def _extract_scenario_bounds(parser: SysMLParser) -> dict:
    inputs = {}
    for parameter in parser.parameters:
        if "ScenarioInput" in parameter.metadata:
            inputs[parameter.qualified_name] = {
                "default": parameter.value,
                "lower": None,
                "upper": None,
            }
    for constraint in parser.parsed_constraints:
        if "ScenarioConstraint" in getattr(constraint, "metadata", []):
            _walk_bounds(constraint.expression, inputs, parser.system_part)
    for qname, info in inputs.items():
        if info["lower"] is None:
            info["lower"] = 0.0
        if info["upper"] is None:
            info["upper"] = info["default"]
        if info["default"] is None:
            raise ValueError(f"ScenarioInput has no default value: {qname}")
        if info["lower"] > info["upper"]:
            raise ValueError(f"ScenarioInput has empty bounds: {qname}")
        if not info["lower"] <= info["default"] <= info["upper"]:
            raise ValueError(f"ScenarioInput default is outside bounds: {qname}")
    return inputs


def _extract_cross_constraints(parser: SysMLParser) -> list:
    constraints = []
    system = parser.system_part
    input_qnames = {
        parameter.qualified_name for parameter in parser.parameters
        if "ScenarioInput" in parameter.metadata
    }
    for constraint in parser.parsed_constraints:
        if "ScenarioConstraint" in getattr(constraint, "metadata", []):
            _walk_cross_constraints(
                constraint.expression, input_qnames, system, constraints
            )
    return constraints


def _walk_cross_constraints(expr, input_qnames, system, out):
    if not isinstance(expr, BinaryExpr):
        return
    if expr.op == "and":
        _walk_cross_constraints(expr.left, input_qnames, system, out)
        _walk_cross_constraints(expr.right, input_qnames, system, out)
        return
    if expr.op in (">=", "<="):
        if isinstance(expr.left, RefExpr) and isinstance(expr.right, RefExpr):
            left_qname = system + "::" + "::".join(expr.left.path)
            right_qname = system + "::" + "::".join(expr.right.path)
            if left_qname in input_qnames and right_qname in input_qnames:
                if expr.op == ">=":
                    out.append((left_qname, right_qname))
                else:
                    out.append((right_qname, left_qname))


def _numeric_literal(node):
    if isinstance(node, LiteralExpr) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, UnaryExpr) and node.op == "-":
        value = _numeric_literal(node.operand)
        return None if value is None else -value
    return None


def _walk_bounds(expr, inputs: dict, system: str):
    if not isinstance(expr, BinaryExpr):
        return
    if expr.op == "and":
        _walk_bounds(expr.left, inputs, system)
        _walk_bounds(expr.right, inputs, system)
        return
    if expr.op not in (">=", "<=", "=="):
        return
    right_value = _numeric_literal(expr.right)
    left_value = _numeric_literal(expr.left)
    if isinstance(expr.left, RefExpr) and right_value is not None:
        ref, literal, op = expr.left, right_value, expr.op
    elif left_value is not None and isinstance(expr.right, RefExpr):
        ref, literal = expr.right, left_value
        op = {">=": "<=", "<=": ">=", "==": "=="}[expr.op]
    else:
        return
    qname = system + "::" + "::".join(ref.path)
    if qname not in inputs:
        return
    if op in ("==", ">="):
        current = inputs[qname]["lower"]
        inputs[qname]["lower"] = max(
            float("-inf") if current is None else current, literal
        )
    if op in ("==", "<="):
        current = inputs[qname]["upper"]
        inputs[qname]["upper"] = (
            literal if current is None else min(current, literal)
        )
