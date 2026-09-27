"""Trainable GRU policy wrapped by a spec-derived Python decision checker."""
import torch
import torch.nn as nn
from shield import SpecShield


class CompositeShieldedPolicy(nn.Module):
    def __init__(self, policy, shield):
        super().__init__()
        self.policy = policy
        self.shield = shield

    def initial_hidden(self, batch_size=1):
        return self.policy.initial_hidden(batch_size)

    def forward_policy(self, obs_t, hidden):
        return self.policy(obs_t, hidden)

    def forward_sequence(self, obs_seq, hidden, mask=None):
        return self.policy.forward_sequence(obs_seq, hidden, mask)

    def act(self, obs_t, hidden, obs_dict, greedy=False):
        with torch.no_grad():
            dist, value, hidden = self.policy(obs_t, hidden)
        proposed = (dist.probs.argmax(dim=-1).item() if greedy
                    else dist.sample().item())
        final_action, overridden = self.shield.select(
            proposed, obs_dict, dist.probs.detach().squeeze(0))
        return final_action, dist, value, hidden, overridden


def build_composite_model(model_path, policy):
    return CompositeShieldedPolicy(policy, SpecShield(model_path))
