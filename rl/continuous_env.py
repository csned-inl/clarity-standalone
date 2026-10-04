"""Continuous-action adapter for the existing SysML simulator environment."""

from __future__ import annotations

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
                 rng_seed: int | None = None):
        super().__init__(model_path, dt=dt, max_steps=max_steps,
                         phase=phase, rng_seed=rng_seed)
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
            "executed_neural_outputs": actuators,
        }
        observation = (None if result.state is None
                       else self._state_to_obs(result.state))
        return observation, reward, done, info

    @property
    def raw_model_inputs(self) -> dict:
        return dict(self._twin._model_inputs)
