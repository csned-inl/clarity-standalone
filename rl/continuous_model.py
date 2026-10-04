"""Continuous-action counterpart of the original CLARITY GRU actor-critic."""

from __future__ import annotations

import torch
import torch.nn as nn
from torch.distributions import Independent, Normal


class ContinuousRecurrentActorCritic(nn.Module):
    """64-wide encoder, GRU state, Gaussian action head, and value head.

    The Gaussian is intentionally unsquashed.  The SysML actuator owns the
    physical voltage saturation, while the specification shield owns the
    source-level controller contract.  Clipping inside the neural policy would
    silently change both the action distribution and its PPO log probability.
    """

    def __init__(self, obs_dim: int, action_dim: int = 1,
                 hidden_dim: int = 64, gru_layers: int = 1):
        super().__init__()
        if obs_dim <= 0 or action_dim <= 0:
            raise ValueError("observation and action dimensions must be positive")
        self.hidden_dim = hidden_dim
        self.gru_layers = gru_layers
        self.action_dim = action_dim

        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.Tanh(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.Tanh(),
        )
        self.gru = nn.GRU(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=gru_layers,
            batch_first=True,
        )
        self.action_mean_head = nn.Linear(hidden_dim, action_dim)
        self.action_log_std = nn.Parameter(torch.zeros(action_dim))
        self.value_head = nn.Linear(hidden_dim, 1)

    def initial_hidden(self, batch_size: int = 1) -> torch.Tensor:
        return torch.zeros(self.gru_layers, batch_size, self.hidden_dim)

    def _distribution(self, mean: torch.Tensor):
        log_std = self.action_log_std.clamp(-5.0, 2.0)
        std = log_std.exp().expand_as(mean)
        return Independent(Normal(mean, std), 1)

    def forward(self, obs: torch.Tensor, hidden: torch.Tensor):
        features = self.encoder(obs).unsqueeze(1)
        recurrent, hidden = self.gru(features, hidden)
        recurrent = recurrent.squeeze(1)
        mean = self.action_mean_head(recurrent)
        value = self.value_head(recurrent)
        return self._distribution(mean), value, hidden

    def forward_sequence(self, obs_sequence: torch.Tensor,
                         hidden: torch.Tensor, mask: torch.Tensor | None = None):
        features = self.encoder(obs_sequence)
        if mask is not None:
            lengths = mask.sum(dim=1).long().clamp_min(1).cpu()
            packed = nn.utils.rnn.pack_padded_sequence(
                features, lengths, batch_first=True, enforce_sorted=False)
            recurrent, _ = self.gru(packed, hidden)
            recurrent, _ = nn.utils.rnn.pad_packed_sequence(
                recurrent, batch_first=True,
                total_length=obs_sequence.shape[1])
        else:
            recurrent, _ = self.gru(features, hidden)
        means = self.action_mean_head(recurrent)
        values = self.value_head(recurrent)
        return self._distribution(means), values


def select_torch_device(requested: str = "auto") -> torch.device:
    """Select CUDA, Apple MPS, or CPU without silently skipping MPS."""
    if requested != "auto":
        device = torch.device(requested)
        if device.type == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but is unavailable")
        if device.type == "mps" and not (
                hasattr(torch.backends, "mps")
                and torch.backends.mps.is_available()):
            raise RuntimeError("Apple MPS was requested but is unavailable")
        return device
    if torch.cuda.is_available():
        return torch.device("cuda")
    if (hasattr(torch.backends, "mps")
            and torch.backends.mps.is_available()):
        return torch.device("mps")
    return torch.device("cpu")
