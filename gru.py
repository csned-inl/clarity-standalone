"""Original GRU oracle-cloning/PPO path with a strict final selection gate."""

from __future__ import annotations

import json
from pathlib import Path

import torch

from composite_model import build_composite_model
from env import SysMLEnv
from oracle import extract_interface
from selection import select
from train import MODE_CONFIG, run_training_mode


def train_and_select(model: Path, out_dir: Path, *, seed: int = 42,
                     max_steps: int = 1200, eval_episodes: int = 100,
                     test_episodes: int = 100,
                     oracle_samples: int = 2000, oracle_epochs: int = 100,
                     ppo_episodes: int = 2000, dt: float = 0.1) -> dict:
    """Train the original GRU, then publish only a safe evaluated checkpoint."""
    if ppo_episodes < 100 or ppo_episodes % 100:
        raise ValueError("PPO episodes must be a positive multiple of 100")
    if min(max_steps, eval_episodes, test_episodes, oracle_samples,
           oracle_epochs) <= 0:
        raise ValueError("training and evaluation counts must be positive")

    torch.set_num_threads(1)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    iface = extract_interface(str(model), dt=dt)
    probe = SysMLEnv(str(model), dt=dt, max_steps=max_steps,
                     phase=1, rng_seed=seed)
    try:
        obs_dim, n_actions = probe.obs_dim, probe.n_actions
    finally:
        probe.close()

    config = dict(MODE_CONFIG["full"])
    config.update(oracle_samples=oracle_samples, oracle_epochs=oracle_epochs,
                  ppo_episodes=ppo_episodes)
    training_dir = out_dir / "training"
    training_dir.mkdir(parents=True, exist_ok=True)
    composite, _legacy_detail, _legacy_passed = run_training_mode(
        "full", build_composite_model, str(model), iface, obs_dim, n_actions,
        device, str(training_dir), config, seed=seed,
        save_all_checkpoints=True, max_steps=max_steps, dt=dt,
    )
    report = select(str(model), composite, training_dir / "full", out_dir,
                    device=device, seed=seed + 30_000,
                    eval_episodes=eval_episodes,
                    test_episodes=test_episodes, max_steps=max_steps, dt=dt)
    report["training"] = {
        "architecture": "64-wide two-layer MLP encoder, 64-unit GRU, "
                        "policy/value heads",
        "oracle_samples": oracle_samples, "oracle_epochs": oracle_epochs,
        "ppo_episodes": ppo_episodes, "checkpoint_interval": 100,
        "observation_dimension": obs_dim, "action_count": n_actions,
        "parameter_count": sum(p.numel() for p in composite.policy.parameters()),
        "seed": seed,
        "dt_seconds": dt,
    }
    (out_dir / "checkpoint_selection.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
