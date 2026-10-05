"""Model-independent definitions for continuous shield-training experiments."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True)
class ContinuousTrainingMode:
    name: str
    use_shield: bool
    credit_action: str
    terminate_on_prohibition: bool

    def __post_init__(self):
        if self.credit_action not in {"executed", "proposal"}:
            raise ValueError(f"invalid credit_action: {self.credit_action}")
        if self.use_shield and self.terminate_on_prohibition:
            raise ValueError(
                "shield intervention is safe and cannot terminate an episode")


TRAINING_MODES = (
    ContinuousTrainingMode(
        "unshielded_safety_terminate", False, "proposal", True),
    ContinuousTrainingMode(
        "shielded_executed_credit", True, "executed", False),
    ContinuousTrainingMode(
        "shielded_proposal_credit", True, "proposal", False),
)


def proposal_penalty(correction: float, *, penalty_cap: float,
                     action_error_scale: float) -> float:
    """Return a bounded, non-flat penalty for deviation from the contract."""
    if not math.isfinite(penalty_cap) or penalty_cap <= 0.0:
        raise ValueError("penalty_cap must be finite and positive")
    if not math.isfinite(action_error_scale) or action_error_scale <= 0.0:
        raise ValueError("action_error_scale must be finite and positive")
    if not math.isfinite(correction) or correction < 0.0:
        return -penalty_cap
    return -penalty_cap * correction / (action_error_scale + correction)


def training_reward(mode: ContinuousTrainingMode, environment_reward: float,
                    correction: float, *, comparison_abs_tol: float,
                    penalty_cap: float, action_error_scale: float,
                    max_steps: int, time_budget: float,
                    override_budget: float) -> float:
    """Choose either environment reward or proposal punishment, never both."""
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    if min(time_budget, override_budget) < 0.0:
        raise ValueError("reward budgets must be nonnegative")
    reward = float(environment_reward)
    intervened = correction > comparison_abs_tol
    if mode.credit_action == "proposal" and intervened:
        return proposal_penalty(
            correction,
            penalty_cap=penalty_cap,
            action_error_scale=action_error_scale,
        )
    if reward > 0.0:
        return reward
    if reward == 0.0:
        return 0.0
    if mode.use_shield and intervened:
        return -override_budget / max_steps
    return -time_budget / max_steps
