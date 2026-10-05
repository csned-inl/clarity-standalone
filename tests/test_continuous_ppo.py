"""Tensor-shape smoke test for recurrent continuous PPO."""

import math
from pathlib import Path
import sys
import unittest

import numpy as np
import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rl"))

from continuous_model import ContinuousRecurrentActorCritic  # noqa: E402
from continuous_ppo import (  # noqa: E402
    ContinuousEpisodeBuffer,
    ContinuousRecurrentPPO,
)


class ContinuousPPOTests(unittest.TestCase):
    def test_gaussian_sequence_update_is_finite(self):
        torch.manual_seed(7)
        model = ContinuousRecurrentActorCritic(
            obs_dim=3, action_dim=1, hidden_dim=8)
        buffer = ContinuousEpisodeBuffer()
        for offset in (0.0, 0.25):
            observations = [
                np.asarray([offset + i, i / 2, -i], dtype=np.float32)
                for i in range(3)
            ]
            buffer.add({
                "observations": observations,
                "actions": [[0.1], [0.0], [-0.1]],
                "rewards": [-0.01, -0.01, 1.0],
                "values": [0.0, 0.0, 0.0],
                "log_prob": [-1.0, -1.0, -1.0],
                "dones": [False, False, True],
            })
        trainer = ContinuousRecurrentPPO(
            model, device=torch.device("cpu"), epochs=1)
        metrics = trainer.update(buffer)
        self.assertEqual(
            set(metrics), {"policy_loss", "value_loss", "entropy"})
        self.assertTrue(all(math.isfinite(value)
                            for value in metrics.values()))


if __name__ == "__main__":
    unittest.main()
