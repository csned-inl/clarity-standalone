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
    def test_only_unshielded_training_has_termination_split(self):
        self.assertEqual(len(TRAINING_MODES), 4)
        shielded = [mode for mode in TRAINING_MODES if mode.use_shield]
        self.assertEqual(len(shielded), 2)
        self.assertTrue(all(
            not mode.terminate_on_unsafe_execution for mode in shielded))
        self.assertEqual(
            {mode.terminate_on_unsafe_execution
             for mode in TRAINING_MODES if not mode.use_shield},
            {False, True})

    def test_proposal_penalty_is_smooth_and_capped(self):
        self.assertEqual(proposal_penalty(
            0.0, penalty_fraction=0.15, action_error_scale=10.0), 0.0)
        self.assertAlmostEqual(proposal_penalty(
            5.0, penalty_fraction=0.15, action_error_scale=10.0), -0.075)
        self.assertEqual(proposal_penalty(
            20.0, penalty_fraction=0.15, action_error_scale=10.0), -0.15)

    def test_executed_credit_does_not_penalize_safe_intervention(self):
        mode = next(
            row for row in TRAINING_MODES
            if row.name == "shielded_executed_credit")
        self.assertEqual(training_reward(
            mode, 1.0, 100.0,
            penalty_fraction=0.15, action_error_scale=10.0), 1.0)

    def test_proposal_credit_retains_safe_execution_reward_and_penalty(self):
        mode = next(
            row for row in TRAINING_MODES
            if row.name == "shielded_proposal_credit")
        self.assertAlmostEqual(training_reward(
            mode, 1.0, 5.0,
            penalty_fraction=0.15, action_error_scale=10.0), 0.925)


if __name__ == "__main__":
    unittest.main()
