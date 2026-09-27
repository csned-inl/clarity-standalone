"""
Gym-style environment wrapping the SysML SimulatorTwin.

Fully general — all structure derived from SysML extraction:
    - Observation space: Neural action in-params
    - Action space: 2^N for N boolean Neural out-params
    - Scenario randomization: bounds from #ScenarioConstraint
    - Normalization: global scale from initial obs values
    - Reward: recorded initialization and completed-cycle requirements
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sysml-models"))

from sysml_parser import SysMLParser, BinaryExpr, RefExpr, LiteralExpr, UnaryExpr
from simulator_adapter import SimulatorTwin
from requirement_events import ResetResult, ResetUnavailable, summarize_events

_SAFETY_KINDS = {"Prohibition", "Obligation", None}


class SysMLEnv:
    """RL environment derived from any SysML model with a #Neural action.

    All dimensions, action mappings, scenario ranges, and normalization
    are read from the parsed SysML model — nothing is hardcoded.
    """

    def __init__(self, model_path: str, dt: float = 0.1,
                 max_steps: int = 1200, phase: int = 1,
                 rng_seed: int = None):
        self._model_path = model_path
        self._twin = SimulatorTwin(model_path, dt=dt)
        self._max_steps = max_steps
        self.phase = phase
        self._step_count = 0
        self._rng = np.random.default_rng(rng_seed)

        parser = self._twin._parser

        # Find #Neural action def and extract in/out params
        self._out_params = []
        self._obs_keys = []
        for pdef in parser.part_defs.values():
            for ad in pdef.action_defs:
                if "Neural" in ad.metadata:
                    self._obs_keys = [p.name for p in ad.in_params]
                    self._out_params = [(p.name, p.type_name) for p in ad.out_params]
                    break
            if self._out_params:
                break

        # Build action map: 2^N for N boolean outputs
        n_out = len(self._out_params)
        self._action_map = {}
        for action_id in range(2 ** n_out):
            actuators = {}
            for bit, (name, _) in enumerate(self._out_params):
                actuators[name] = bool(action_id & (1 << bit))
            self._action_map[action_id] = actuators

        self.obs_dim = len(self._obs_keys)
        self.n_actions = len(self._action_map)

        # Extract scenario inputs with bounds from ScenarioConstraint
        self._scenario_inputs = _extract_scenario_bounds(parser)

        # Extract cross-parameter constraints (e.g. originalLevel >= transferTarget)
        self._cross_constraints = _extract_cross_constraints(parser)

        # Compute global normalization scale from initial obs
        self._obs_scale = self._compute_obs_scale()

    def _compute_obs_scale(self):
        """Run one init step and use max absolute obs value as global scale."""
        self._twin()  # reset
        state = self._twin(self._action_map[0])  # step with no-op
        scale = 1.0
        for key in self._obs_keys:
            val = state.get(key, 0.0)
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                scale = max(scale, abs(val))
        return scale

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
        # Enforce cross-parameter constraints by clamping.
        # For each (greater, lesser) pair: if greater < lesser, clamp
        # lesser down to greater's value.
        for greater_qname, lesser_qname in self._cross_constraints:
            g = values.get(greater_qname, 0)
            l = values.get(lesser_qname, 0)
            if g < l + 5:
               values[lesser_qname] = max(g - 5, self._scenario_inputs[lesser_qname]["lower"])
        # Sync physical state to match randomized scenario inputs
        for qname, info in self._scenario_inputs.items():
            if "OriginalLevel" in qname:
                # Find the matching physical tank state key
                for parameter in self._twin.parser.parameters:
                    key = parameter.qualified_name
                    if "currentLevelMl" in key:
                        # Match by tank number
                        for digit in "0123456789":
                            if digit in qname and digit in key:
                                values[key] = values[qname]
                                break
        return values

    def _state_to_obs(self, state: dict) -> np.ndarray:
        """Convert twin state dict to normalized observation vector."""
        obs = []
        for key in self._obs_keys:
            val = state.get(key, 0.0)
            if isinstance(val, bool):
                obs.append(float(val))
            else:
                obs.append(float(val) / self._obs_scale)
        return np.array(obs, dtype=np.float32)

    def reset_with_result(self, seed: int = None):
        if seed is not None:
            self._rng = np.random.default_rng(seed)
        self._step_count = 0
        self._twin.prepare(self._sample_scenario())
        result = self._twin.start()
        statuses = summarize_events(result.events)
        outcome = result.outcome
        if result.error or any(row['errors'] for row in statuses.values()):
            outcome = 'error'
        elif self.phase == 2 and any(row['status'] is False for row in statuses.values()):
            outcome = 'violation'
        observation = self._state_to_obs(result.state) if outcome == 'decision' else None
        self.reset_result = ResetResult(observation, outcome, result.events, result.error)
        self._episode_done = outcome != 'decision'
        return self.reset_result

    def reset(self, seed: int = None) -> np.ndarray:
        result = self.reset_with_result(seed)
        if result.outcome != 'decision':
            raise ResetUnavailable(result)
        return result.observation

    def step(self, action: int) -> tuple[np.ndarray, float, bool, dict]:
        """Take one step. Returns (obs, reward, done, info)."""
        if self._episode_done:
            raise RuntimeError('cannot act after terminal/error/reset failure')
        actuators = self._action_map[action]
        result = self._twin.advance(actuators)
        self._step_count += 1
        statuses = summarize_events(result.events)
        errors = {name: row['errors'] for name, row in statuses.items() if row['errors']}
        if errors or result.error:
            reward, done, outcome = 0.0, True, 'ERROR'
        elif self.phase == 2 and any(row['status'] is False for row in statuses.values()):
            reward, done, outcome = -1.0, True, 'VIOLATION'
        elif result.outcome == 'terminal':
            reward, done, outcome = 1.0, True, 'SUCCESS'
        else:
            reward, done, outcome = -0.01, False, 'RUNNING'
        truncated = self._step_count >= self._max_steps and not done
        if truncated:
            reward, done, outcome = 0.0, True, 'TRUNCATED'
        self._episode_done = done
        info = {'step': self._step_count, 'state': result.state, 'statuses': statuses,
                'requirement_events': result.events, 'error': result.error,
                'evaluation_errors': errors, 'outcome': outcome, 'truncated': truncated}
        observation = None if result.state is None else self._state_to_obs(result.state)
        return observation, reward, done, info

    def close(self):
        """Clean up simulator thread."""
        self._twin._stop()


# ---------------------------------------------------------------------------
# ScenarioConstraint bound extraction
# ---------------------------------------------------------------------------

def _extract_scenario_bounds(parser: SysMLParser) -> dict:
    """Extract per-ScenarioInput bounds from #ScenarioConstraint expressions.

    Returns dict mapping qualified_name -> {default, lower, upper}.
    """
    inputs = {}
    for p in parser.parameters:
        if "ScenarioInput" in p.metadata:
            inputs[p.qualified_name] = {
                "default": p.value,
                "lower": None,
                "upper": None,
            }

    # Walk ScenarioConstraint expressions for constant bounds
    for constraint in parser.parsed_constraints:
        if 'ScenarioConstraint' in getattr(constraint, 'metadata', []):
            _walk_bounds(constraint.expression, inputs, parser.system_part)

    # Fill missing bounds with sensible defaults
    for qname, info in inputs.items():
        if info["lower"] is None:
            info["lower"] = 0.0
        if info["upper"] is None:
            info["upper"] = info["default"]

    return inputs


def _extract_cross_constraints(parser: SysMLParser) -> list:
    """Extract var >= var constraints from #ScenarioConstraint.

    Returns list of (greater_qname, lesser_qname) pairs meaning
    greater_qname >= lesser_qname must hold after sampling.
    """
    constraints = []
    system = parser.system_part

    # Collect ScenarioInput qnames for matching
    input_qnames = set()
    for p in parser.parameters:
        if "ScenarioInput" in p.metadata:
            input_qnames.add(p.qualified_name)

    for constraint in parser.parsed_constraints:
        if 'ScenarioConstraint' in getattr(constraint, 'metadata', []):
            _walk_cross_constraints(
                constraint.expression, input_qnames, system, constraints)

    return constraints


def _walk_cross_constraints(expr, input_qnames, system, out):
    """Extract var >= var constraints recursively."""
    if not isinstance(expr, BinaryExpr):
        return
    if expr.op == 'and':
        _walk_cross_constraints(expr.left, input_qnames, system, out)
        _walk_cross_constraints(expr.right, input_qnames, system, out)
        return

    if expr.op in ('>=', '<='):
        if isinstance(expr.left, RefExpr) and isinstance(expr.right, RefExpr):
            left_qname = system + "::" + "::".join(expr.left.path)
            right_qname = system + "::" + "::".join(expr.right.path)
            if left_qname in input_qnames and right_qname in input_qnames:
                if expr.op == '>=':
                    out.append((left_qname, right_qname))
                else:
                    out.append((right_qname, left_qname))


def _walk_bounds(expr, inputs: dict, system: str):
    """Recursively extract constant bounds from a constraint AST."""
    if not isinstance(expr, BinaryExpr):
        return
    if expr.op == 'and':
        _walk_bounds(expr.left, inputs, system)
        _walk_bounds(expr.right, inputs, system)
        return

    # var >= const  →  lower bound
    # var <= const  →  upper bound
    # var == const  →  fixed (lower = upper = const)
    if expr.op in ('>=', '<=', '=='):
        ref, lit = None, None
        def numeric_literal(node):
            if isinstance(node, LiteralExpr) and type(node.value) in (int, float):
                return node.value
            if isinstance(node, UnaryExpr) and node.op == '-':
                value = numeric_literal(node.operand)
                return None if value is None else -value
            return None
        right_value = numeric_literal(expr.right)
        left_value = numeric_literal(expr.left)
        if isinstance(expr.left, RefExpr) and right_value is not None:
            ref, lit, op = expr.left, right_value, expr.op
        elif left_value is not None and isinstance(expr.right, RefExpr):
            ref, lit = expr.right, left_value
            op = {'>=': '<=', '<=': '>=', '==': '=='}[expr.op]
        else:
            return

        qname = system + "::" + "::".join(ref.path)
        if qname not in inputs:
            return

        if op == '==' or op == '>=':
            cur = inputs[qname]["lower"]
            inputs[qname]["lower"] = max(
                float('-inf') if cur is None else cur, lit)
        if op == '==' or op == '<=':
            cur = inputs[qname]["upper"]
            inputs[qname]["upper"] = lit if cur is None else min(cur, lit)
