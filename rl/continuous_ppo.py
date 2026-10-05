"""Small recurrent PPO implementation for continuous Gaussian actions."""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn


def _gae(rewards, values, dones, gamma: float, lam: float):
    advantages = [0.0] * len(rewards)
    carry = 0.0
    for index in reversed(range(len(rewards))):
        next_value = values[index + 1] if index + 1 < len(values) else 0.0
        nonterminal = 0.0 if dones[index] else 1.0
        delta = rewards[index] + gamma * next_value * nonterminal - values[index]
        carry = delta + gamma * lam * nonterminal * carry
        advantages[index] = carry
    return advantages, [a + v for a, v in zip(advantages, values)]


class ContinuousEpisodeBuffer:
    def __init__(self):
        self.episodes = []

    def add(self, episode):
        if not episode["observations"]:
            raise ValueError("cannot add an empty episode")
        self.episodes.append(episode)

    def clear(self):
        self.episodes.clear()

    def batch(self, *, gamma: float, lam: float, device: torch.device):
        batch_size = len(self.episodes)
        maximum = max(len(row["observations"]) for row in self.episodes)
        obs_dim = len(self.episodes[0]["observations"][0])
        action_dim = len(self.episodes[0]["actions"][0])
        observations = np.zeros(
            (batch_size, maximum, obs_dim), dtype=np.float32)
        actions = np.zeros(
            (batch_size, maximum, action_dim), dtype=np.float32)
        old_log_prob = np.zeros((batch_size, maximum), dtype=np.float32)
        advantages = np.zeros((batch_size, maximum), dtype=np.float32)
        returns = np.zeros((batch_size, maximum), dtype=np.float32)
        mask = np.zeros((batch_size, maximum), dtype=np.float32)
        for index, episode in enumerate(self.episodes):
            length = len(episode["observations"])
            advance, target = _gae(
                episode["rewards"], episode["values"], episode["dones"],
                gamma, lam)
            observations[index, :length] = episode["observations"]
            actions[index, :length] = episode["actions"]
            old_log_prob[index, :length] = episode["log_prob"]
            advantages[index, :length] = advance
            returns[index, :length] = target
            mask[index, :length] = 1.0
        valid = mask.astype(bool)
        values = advantages[valid]
        if len(values) > 1:
            advantages[valid] = (
                values - values.mean()) / (values.std() + 1e-8)
        tensor = lambda value: torch.as_tensor(value, device=device)
        return {
            "observations": tensor(observations),
            "actions": tensor(actions),
            "old_log_prob": tensor(old_log_prob),
            "advantages": tensor(advantages),
            "returns": tensor(returns),
            "mask": tensor(mask),
        }


class ContinuousRecurrentPPO:
    def __init__(self, model, *, device: torch.device, learning_rate=3e-4,
                 gamma=0.99, lam=0.95, clip=0.2, entropy=0.001,
                 value_weight=0.5, epochs=4, max_gradient_norm=0.5):
        self.model = model.to(device)
        self.device = device
        self.optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
        self.gamma = gamma
        self.lam = lam
        self.clip = clip
        self.entropy = entropy
        self.value_weight = value_weight
        self.epochs = epochs
        self.max_gradient_norm = max_gradient_norm

    def update(self, buffer: ContinuousEpisodeBuffer):
        batch = buffer.batch(
            gamma=self.gamma, lam=self.lam, device=self.device)
        observations = batch["observations"]
        actions = batch["actions"]
        old_log_prob = batch["old_log_prob"]
        advantages = batch["advantages"]
        returns = batch["returns"]
        mask = batch["mask"]
        totals = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0}
        for _ in range(self.epochs):
            hidden = self.model.initial_hidden(observations.shape[0]).to(
                self.device)
            distribution, predicted = self.model.forward_sequence(
                observations, hidden, mask)
            predicted = predicted.squeeze(-1)
            new_log_prob = distribution.log_prob(actions)
            entropy = distribution.entropy()
            ratio = torch.exp(new_log_prob - old_log_prob)
            first = ratio * advantages
            second = torch.clamp(
                ratio, 1.0 - self.clip, 1.0 + self.clip) * advantages
            policy_loss = -torch.minimum(first, second)
            value_loss = (predicted - returns).pow(2)
            loss = (policy_loss + self.value_weight * value_loss
                    - self.entropy * entropy)
            denominator = mask.sum().clamp_min(1.0)
            loss = (loss * mask).sum() / denominator
            self.optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(
                self.model.parameters(), self.max_gradient_norm)
            self.optimizer.step()
            totals["policy_loss"] += float(
                (policy_loss * mask).sum().item() / denominator.item())
            totals["value_loss"] += float(
                (value_loss * mask).sum().item() / denominator.item())
            totals["entropy"] += float(
                (entropy * mask).sum().item() / denominator.item())
        return {name: value / self.epochs for name, value in totals.items()}
