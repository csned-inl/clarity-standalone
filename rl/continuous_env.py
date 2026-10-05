"""Continuous-action adapter for the existing SysML simulator environment."""

from __future__ import annotations

import math
import numpy as np

from env import SysMLEnv
from requirement_events import summarize_events


class ContinuousSysMLEnv(SysMLEnv):
    """Reuse scenario, observation, reset, and requirement semantics.

    Only action encoding changes: a length-N real vector becomes the neural
    output dictionary consumed by ``SimulatorTwin``.  No action grid is built.
    """

    def __init__(self, model_path: str, dt: float = 0.1,
                 max_steps: int = 1200, phase: int = 1,
                 rng_seed: int | None = None, *,
                 terminate_on_violation: bool = True,
                 violation_penalty: float = 1.0,
                 terminating_metadata: frozenset[str] | None = None,
                 observation_scales: dict[str, float] | None = None):
        super().__init__(model_path, dt=dt, max_steps=max_steps,
                         phase=phase, rng_seed=rng_seed,
                         observation_scales=observation_scales)
        if (not math.isfinite(violation_penalty)
                or violation_penalty < 0.0):
            raise ValueError("violation_penalty must be finite and nonnegative")
        self.terminate_on_violation = bool(terminate_on_violation)
        self.violation_penalty = float(violation_penalty)
        self.terminating_metadata = terminating_metadata
        if terminating_metadata is None:
            self._terminating_requirement_names = None
        else:
            self._terminating_requirement_names = {
                requirement.name
                for requirement in self._twin.parser.parsed_requirements
                if set(requirement.metadata) & set(terminating_metadata)
            }
        if not self._out_params:
            raise ValueError("model has no #Neural outputs")
        unsupported = [(name, type_name) for name, type_name in self._out_params
                       if type_name != "Real"]
        if unsupported:
            raise ValueError(
                f"continuous environment requires Real outputs: {unsupported}")
        self.action_names = tuple(name for name, _ in self._out_params)
        self.action_dim = len(self.action_names)
        # A finite action count would be false for this environment.
        self.n_actions = None

    def step(self, action):
        if self._episode_done:
            raise RuntimeError("cannot act after terminal/error/reset failure")
        values = np.asarray(action, dtype=np.float64).reshape(-1)
        if len(values) != self.action_dim:
            raise ValueError(
                f"expected {self.action_dim} continuous actions, got {len(values)}")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"continuous action contains non-finite values: {values}")
        actuators = {name: float(values[index])
                     for index, name in enumerate(self.action_names)}

        result = self._twin.advance(actuators)
        self._step_count += 1
        statuses = summarize_events(result.events)
        errors = {name: row["errors"] for name, row in statuses.items()
                  if row["errors"]}
        violated_names = {
            name for name, row in statuses.items()
            if row["status"] is False
        }
        terminating_names = (
            violated_names
            if self._terminating_requirement_names is None
            else violated_names & self._terminating_requirement_names)
        violated = self.phase == 2 and bool(terminating_names)
        if errors or result.error:
            reward, done, outcome = 0.0, True, "ERROR"
        elif violated:
            reward = -self.violation_penalty
            done = self.terminate_on_violation or result.outcome == "terminal"
            if self.terminate_on_violation:
                outcome = "VIOLATION"
            elif result.outcome == "terminal":
                outcome = "TERMINAL_VIOLATION"
            else:
                outcome = "RUNNING_VIOLATION"
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
            "unsafe_executed": violated,
            "violated_requirements": sorted(violated_names),
            "terminating_violations": sorted(terminating_names),
            "executed_neural_outputs": actuators,
        }
        observation = (None if result.state is None
                       else self._state_to_obs(result.state))
        return observation, reward, done, info

    @property
    def raw_model_inputs(self) -> dict:
        return dict(self._twin._model_inputs)
