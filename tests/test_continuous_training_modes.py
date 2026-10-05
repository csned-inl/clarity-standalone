"""Reward and termination semantics for continuous shield experiments."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rl"))

from continuous_training_modes import (  # noqa: E402
    TRAINING_MODES,
    proposal_penalty,
    training_reward,
)


class ContinuousTrainingModeTests(unittest.TestCase):
    def reward(self, mode, environment_reward, correction):
        return training_reward(
            mode, environment_reward, correction,
            comparison_abs_tol=1e-6,
            penalty_cap=1.0,
            action_error_scale=10.0,
            max_steps=6000,
            time_budget=0.10,
            override_budget=0.05,
        )

    def test_only_unshielded_mode_terminates_on_prohibition(self):
        self.assertEqual(len(TRAINING_MODES), 3)
        shielded = [mode for mode in TRAINING_MODES if mode.use_shield]
        self.assertEqual(len(shielded), 2)
        self.assertTrue(all(
            not mode.terminate_on_prohibition for mode in shielded))
        unshielded = [mode for mode in TRAINING_MODES if not mode.use_shield]
        self.assertEqual(len(unshielded), 1)
        self.assertTrue(unshielded[0].terminate_on_prohibition)

    def test_proposal_penalty_is_smooth_and_capped(self):
        self.assertEqual(proposal_penalty(
            0.0, penalty_cap=1.0, action_error_scale=10.0), 0.0)
        self.assertAlmostEqual(proposal_penalty(
            5.0, penalty_cap=1.0, action_error_scale=10.0), -1.0 / 3.0)
        self.assertAlmostEqual(proposal_penalty(
            20.0, penalty_cap=1.0, action_error_scale=10.0), -2.0 / 3.0)
        self.assertGreater(proposal_penalty(
            1_000.0, penalty_cap=1.0, action_error_scale=10.0), -1.0)

    def test_terminal_success_is_not_mixed_with_override_punishment(self):
        mode = next(
            row for row in TRAINING_MODES
            if row.name == "shielded_executed_credit")
        self.assertEqual(self.reward(mode, 1.0, 100.0), 1.0)

    def test_override_and_time_costs_are_horizon_normalized(self):
        mode = next(
            row for row in TRAINING_MODES
            if row.name == "shielded_executed_credit")
        self.assertAlmostEqual(
            self.reward(mode, -0.01, 1.0), -0.05 / 6000)
        self.assertAlmostEqual(
            self.reward(mode, -0.01, 0.0), -0.10 / 6000)

    def test_proposal_punishment_replaces_environment_reward(self):
        mode = next(
            row for row in TRAINING_MODES
            if row.name == "shielded_proposal_credit")
        self.assertAlmostEqual(
            self.reward(mode, 1.0, 5.0), -1.0 / 3.0)

    def test_compliant_proposal_receives_reward_without_punishment(self):
        mode = next(
            row for row in TRAINING_MODES
            if row.name == "shielded_proposal_credit")
        self.assertEqual(self.reward(mode, 1.0, 0.0), 1.0)


if __name__ == "__main__":
    unittest.main()
