"""Projection shield for the reviewed Hall-motor NeuralRequirement."""

from __future__ import annotations

import math
from pathlib import Path

from hall_motor_verification import MODEL, compile_contract


class HallMotorProjectionShield:
    """Project a proposal onto the model's bounded, Hall-valid action set."""

    def __init__(self, model_path: str | Path = MODEL, *,
                 comparison_abs_tol: float = 1e-6):
        if not math.isfinite(comparison_abs_tol) or comparison_abs_tol < 0.0:
            raise ValueError("comparison_abs_tol must be finite and nonnegative")
        self.contract = compile_contract(Path(model_path))
        self.comparison_abs_tol = float(comparison_abs_tol)

    def select(self, proposed_action: float, observation: dict):
        if "hallCode" not in observation:
            raise KeyError("motor shield requires the Neural input hallCode")
        hall_code = observation["hallCode"]
        if type(hall_code) not in (int, float) or not math.isfinite(float(hall_code)):
            raise ValueError(f"invalid hallCode: {hall_code!r}")
        proposal = float(proposed_action)
        if not math.isfinite(proposal):
            executed = 0.0
            correction = math.inf
        elif int(hall_code) not in self.contract.valid_hall_codes:
            executed = 0.0
            correction = abs(proposal)
        else:
            bound = self.contract.maximum_duty_magnitude
            executed = min(bound, max(-bound, proposal))
            correction = abs(proposal - executed)
        intervened = correction > self.comparison_abs_tol
        return executed, intervened, correction

    def report(self) -> dict:
        return {
            "contract_kind": "bounded_real_with_invalid_hall_zero",
            "output_name": "proposedSignedDutyFraction",
            "bound": self.contract.maximum_duty_magnitude,
            "valid_hall_codes": list(self.contract.valid_hall_codes),
            "execution_rule": "clip valid-Hall proposals; zero invalid-Hall proposals",
            "scope": (
                "neural proposal contract only; the SysML drive independently "
                "projects executed duty onto its exact-model current-safe interval"
            ),
        }
