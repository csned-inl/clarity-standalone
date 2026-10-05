"""GRU warm-start production for an exact continuous SysML contract.

This is the continuous analogue of CLARITY's oracle-cloning phase.  It does
not mislabel exact-contract cloning as autonomous RL: every rollout executes
the source-required action through the symbolic shield, and the network learns
to approximate that action.  Reward optimization should be added only after a
permissive safe-action relation exists.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import shutil
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sysml-models"))

from continuous_env import ContinuousSysMLEnv
from continuous_model import ContinuousRecurrentActorCritic, select_torch_device
from continuous_spec import ExactContinuousShield
from execution_parameters import load_execution_parameters


class ContinuousShieldedPolicy(nn.Module):
    def __init__(self, policy: ContinuousRecurrentActorCritic,
                 shield: ExactContinuousShield):
        super().__init__()
        self.policy = policy
        self.shield = shield

    def initial_hidden(self, batch_size: int = 1):
        return self.policy.initial_hidden(batch_size)

    def act(self, observation_tensor, hidden, raw_observation, *, greedy=False):
        with torch.no_grad():
            distribution, value, hidden = self.policy(
                observation_tensor, hidden)
        proposed_tensor = (distribution.mean if greedy
                           else distribution.sample())
        proposed = float(proposed_tensor.reshape(-1)[0].item())
        executed, overridden, correction = self.shield.select(
            proposed, raw_observation)
        return (np.asarray([executed], dtype=np.float64), distribution, value,
                hidden, overridden, correction, proposed)


def generate_oracle_data(env: ContinuousSysMLEnv,
                         shield: ExactContinuousShield,
                         n_samples: int, *, max_steps: int) -> tuple[np.ndarray, np.ndarray]:
    """Collect reachable observations labeled by the source equality."""
    if n_samples <= 0 or max_steps <= 0:
        raise ValueError("sample and step counts must be positive")
    observations: list[np.ndarray] = []
    actions: list[list[float]] = []
    while len(observations) < n_samples:
        normalized = env.reset()
        for _ in range(max_steps):
            raw = env.raw_model_inputs
            required = shield.required_action(raw)
            observations.append(normalized.copy())
            actions.append([required])
            if len(observations) >= n_samples:
                break
            normalized, _reward, done, info = env.step([required])
            if info["outcome"] == "ERROR":
                raise RuntimeError(
                    info["error"] or str(info["evaluation_errors"]))
            if done:
                break
    return (np.asarray(observations, dtype=np.float32),
            np.asarray(actions, dtype=np.float32))


def clone_exact_feedback(composite: ContinuousShieldedPolicy,
                         observations: np.ndarray, actions: np.ndarray,
                         *, device: torch.device, epochs: int,
                         batch_size: int = 512, learning_rate: float = 1e-3,
                         seed: int = 42) -> list[dict]:
    if epochs <= 0 or batch_size <= 0:
        raise ValueError("epoch and batch counts must be positive")
    rng = np.random.default_rng(seed)
    optimizer = torch.optim.Adam(
        composite.policy.parameters(), lr=learning_rate)
    criterion = nn.MSELoss()
    history = []
    composite.policy.train()

    for epoch in range(1, epochs + 1):
        permutation = rng.permutation(len(observations))
        total_squared_error = 0.0
        sample_count = 0
        for start in range(0, len(permutation), batch_size):
            indices = permutation[start:start + batch_size]
            batch_obs = torch.as_tensor(
                observations[indices], dtype=torch.float32, device=device)
            batch_actions = torch.as_tensor(
                actions[indices], dtype=torch.float32, device=device)
            hidden = composite.initial_hidden(len(indices)).to(device)
            distribution, _value, _hidden = composite.policy(
                batch_obs, hidden)
            prediction = distribution.mean
            loss = criterion(prediction, batch_actions)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(composite.policy.parameters(), 1.0)
            optimizer.step()
            total_squared_error += loss.item() * len(indices)
            sample_count += len(indices)
        row = {
            "epoch": epoch,
            "mean_squared_error": total_squared_error / sample_count,
        }
        history.append(row)
        print(f"  [Continuous oracle] epoch {epoch}/{epochs} "
              f"mse={row['mean_squared_error']:.8f}", flush=True)
    return history


def evaluate_shielded(model_path: str, composite: ContinuousShieldedPolicy,
                      *, device: torch.device, episodes: int, max_steps: int,
                      dt: float, seed: int) -> dict:
    env = ContinuousSysMLEnv(
        model_path, dt=dt, max_steps=max_steps, phase=2, rng_seed=seed)
    composite.policy.eval()
    successes = violations = errors = steps = corrections = 0
    absolute_correction = 0.0
    maximum_correction = 0.0
    messages: list[str] = []
    try:
        for _episode in range(episodes):
            try:
                observation = env.reset()
                hidden = composite.initial_hidden(1).to(device)
                done = False
                last_reward = 0.0
                episode_violated = False
                while not done:
                    tensor = torch.as_tensor(
                        observation, dtype=torch.float32,
                        device=device).unsqueeze(0)
                    (action, _distribution, _value, hidden, overridden,
                     correction, _proposed) = composite.act(
                        tensor, hidden, env.raw_model_inputs, greedy=True)
                    observation, last_reward, done, info = env.step(action)
                    steps += 1
                    corrections += int(overridden)
                    absolute_correction += correction
                    maximum_correction = max(maximum_correction, correction)
                    if info["outcome"] == "ERROR":
                        raise RuntimeError(
                            info["error"] or str(info["evaluation_errors"]))
                    episode_violated |= any(
                        row["status"] is False
                        for row in info["statuses"].values())
                successes += int(last_reward > 0.0)
                violations += int(episode_violated)
            except Exception as exc:
                errors += 1
                messages.append(f"{type(exc).__name__}: {exc}")
                break
    finally:
        env.close()
        composite.policy.train()
    return {
        "episodes_requested": episodes,
        "successes": successes,
        "safety_violation_episodes": violations,
        "evaluation_errors": errors,
        "error_messages": messages,
        "total_steps": steps,
        "corrected_proposals": corrections,
        "correction_rate": corrections / max(steps, 1),
        "mean_absolute_voltage_correction": absolute_correction / max(steps, 1),
        "maximum_absolute_voltage_correction": maximum_correction,
    }


def train_exact_feedback_clone(model: Path, out_dir: Path, *,
                               seed: int = 42, max_steps: int = 6000,
                               oracle_samples: int = 2000,
                               oracle_epochs: int = 100,
                               eval_episodes: int = 100,
                               dt: float | None = None,
                               device_name: str = "auto") -> dict:
    """Train and gate the first continuous GRU artifact.

    The published artifact is explicitly a shield-dependent warm start.  It is
    never labeled as an autonomous safe policy.
    """
    execution = load_execution_parameters(model)
    dt = (execution.integration_step_float if dt is None else
          execution.require_matching_integration_step(dt))
    out_dir.mkdir(parents=True, exist_ok=False)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    device = select_torch_device(device_name)
    shield = ExactContinuousShield(str(model))
    env = ContinuousSysMLEnv(
        str(model), dt=dt, max_steps=max_steps, phase=1, rng_seed=seed)
    try:
        policy = ContinuousRecurrentActorCritic(
            obs_dim=env.obs_dim, action_dim=env.action_dim,
            hidden_dim=64).to(device)
        composite = ContinuousShieldedPolicy(policy, shield).to(device)
        observations, actions = generate_oracle_data(
            env, shield, oracle_samples, max_steps=max_steps)
    finally:
        env.close()

    history = clone_exact_feedback(
        composite, observations, actions, device=device,
        epochs=oracle_epochs, seed=seed)
    checkpoint_dir = out_dir / "training"
    checkpoint_dir.mkdir()
    warm_start = checkpoint_dir / "oracle_warm_start.pt"
    torch.save(composite.policy.state_dict(), warm_start)

    evaluation = evaluate_shielded(
        str(model), composite, device=device, episodes=eval_episodes,
        max_steps=max_steps, dt=dt, seed=seed + 10_000)
    report = {
        "method": "continuous_gru_exact_feedback_clone",
        "architecture": "64-wide two-layer MLP encoder, 64-unit GRU, "
                        "Gaussian scalar-action head, value head",
        "device": str(device),
        "seed": seed,
        "execution_parameters": execution.as_dict(),
        "integration_step_seconds": dt,
        "oracle_samples": oracle_samples,
        "oracle_epochs": oracle_epochs,
        "observation_dimension": len(shield.interface.input_names),
        "action_dimension": 1,
        "parameter_count": sum(
            parameter.numel() for parameter in composite.policy.parameters()),
        "requires_runtime_shield": True,
        "learned_policy_autonomous": False,
        "training_history": history,
        "evaluation": evaluation,
        "final_model": None,
    }
    if (evaluation["safety_violation_episodes"]
            or evaluation["evaluation_errors"]):
        (out_dir / "training_report.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise RuntimeError(
            "shielded continuous GRU failed evaluation; no final artifact")

    final_dir = out_dir / "final"
    final_dir.mkdir()
    final_model = final_dir / "shielded_policy.pt"
    shutil.copyfile(warm_start, final_model)
    model_sha256 = hashlib.sha256(model.read_bytes()).hexdigest()
    deployment = {
        "policy": final_model.name,
        "source_model": str(model.resolve()),
        "source_model_sha256": model_sha256,
        "execution_parameters": execution.as_dict(),
        "shield_contract": shield.report(),
        "requires_runtime_shield": True,
        "learned_policy_autonomous": False,
    }
    (final_dir / "deployment.json").write_text(
        json.dumps(deployment, indent=2, sort_keys=True) + "\n")
    report["final_model"] = str(final_model.resolve())
    report["deployment_manifest"] = str(
        (final_dir / "deployment.json").resolve())
    (out_dir / "training_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
