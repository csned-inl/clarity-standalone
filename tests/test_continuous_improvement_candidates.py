"""Focused checks for continuous training improvement components."""

import math
from pathlib import Path
import sys
import unittest

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rl"))

from continuous_model import (  # noqa: E402
    BoundedMeanContinuousRecurrentActorCritic,
    ContinuousFeedForwardActorCritic,
)


class ContinuousImprovementCandidateTests(unittest.TestCase):
    def test_bounded_mean_preserves_gaussian_log_probability(self):
        model = BoundedMeanContinuousRecurrentActorCritic(
            obs_dim=3, action_dim=1, hidden_dim=8, action_limit=10.0)
        with torch.no_grad():
            model.action_mean_head.weight.zero_()
            model.action_mean_head.bias.fill_(1000.0)
        observation = torch.zeros(2, 3)
        hidden = model.initial_hidden(2)
        distribution, _value, _hidden = model(observation, hidden)
        self.assertTrue(torch.all(distribution.mean <= 10.0))
        self.assertTrue(torch.all(distribution.mean >= -10.0))
        log_probability = distribution.log_prob(distribution.mean)
        self.assertTrue(all(math.isfinite(float(value))
                            for value in log_probability))

    def test_feedforward_candidate_carries_no_temporal_state(self):
        model = ContinuousFeedForwardActorCritic(
            obs_dim=3, action_dim=1, hidden_dim=8)
        observation = torch.randn(2, 3)
        first, first_value, _ = model(
            observation, torch.randn(1, 2, 1))
        second, second_value, _ = model(
            observation, torch.randn(1, 2, 1))
        self.assertTrue(torch.equal(first.mean, second.mean))
        self.assertTrue(torch.equal(first_value, second_value))

        sequence = observation.unsqueeze(1).repeat(1, 4, 1)
        distribution, values = model.forward_sequence(
            sequence, model.initial_hidden(2))
        self.assertEqual(distribution.mean.shape, (2, 4, 1))
        self.assertEqual(values.shape, (2, 4, 1))


if __name__ == "__main__":
    unittest.main()
