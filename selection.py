"""Evaluate GRU checkpoints and publish only a zero-violation policy."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import torch

from env import SysMLEnv


class NoSafeCheckpoint(RuntimeError):
    pass


def evaluate_gru(model_path: str, composite, *, device, seed: int,
                 episodes: int, max_steps: int, dt: float = 0.1) -> dict:
    if episodes <= 0:
        raise ValueError("evaluation episodes must be positive")
    env = SysMLEnv(model_path, dt=dt, max_steps=max_steps, phase=2,
                   rng_seed=seed)
    composite.policy.eval()
    n_success = n_safety = n_errors = n_overrides = n_steps = n_completed = 0
    errors = []
    failed_requirements = {}
    try:
        with torch.no_grad():
            for _episode in range(episodes):
                try:
                    initial = env.reset_with_result()
                    if initial.error or initial.errors:
                        raise RuntimeError(initial.error or str(initial.errors))
                    if initial.violations:
                        n_safety += 1
                        n_completed += 1
                        for name in initial.violations:
                            failed_requirements[name] = failed_requirements.get(name, 0) + 1
                        continue
                    if initial.outcome != 'decision':
                        raise RuntimeError(f'reset ended with {initial.outcome}')
                    observation = initial.observation
                    hidden = composite.initial_hidden(1).to(device)
                    done = False
                    last_reward = 0.0
                    episode_violated = False
                    while not done:
                        obs_tensor = torch.as_tensor(
                            observation, dtype=torch.float32,
                            device=device).unsqueeze(0)
                        raw = env._twin._model_inputs
                        action, _dist, _value, hidden, overridden = composite.act(
                            obs_tensor, hidden, raw, greedy=True)
                        observation, last_reward, done, _info = env.step(action)
                        n_steps += 1
                        n_overrides += int(overridden)
                        statuses = _info['statuses']
                        if _info['outcome'] == 'ERROR':
                            raise RuntimeError(_info['error'] or str(_info['evaluation_errors']))
                        for name, row in statuses.items():
                            if not row["status"]:
                                failed_requirements[name] = failed_requirements.get(name, 0) + 1
                                episode_violated = True
                    n_success += int(last_reward > 0)
                    n_safety += int(episode_violated)
                    n_completed += 1
                except Exception as exc:
                    n_errors += 1
                    errors.append(f"{type(exc).__name__}: {exc}")
                    # A failed simulator episode cannot justify any model.
                    break
    finally:
        env.close()
        composite.policy.train()
    return {
        "episodes_requested": episodes,
        "episodes_completed": n_completed,
        "safety_violation_episodes": n_safety,
        "evaluation_errors": n_errors,
        "error_messages": errors,
        "failed_requirement_checks": failed_requirements,
        "successes": n_success,
        "task_errors": episodes - n_success,
        "task_error_rate": (episodes - n_success) / episodes,
        "total_steps": n_steps,
        "shield_overrides": n_overrides,
        "shield_override_rate": n_overrides / max(n_steps, 1),
    }


def select(model_path: str, composite, checkpoint_dir: Path,
           out_dir: Path, *, device, seed: int, eval_episodes: int,
           test_episodes: int, max_steps: int, dt: float = 0.1) -> dict:
    """Rank safe periodic checkpoints by task errors, then shield overrides."""
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_paths = sorted(checkpoint_dir.glob("ep_*.pt"))
    if not checkpoint_paths:
        raise NoSafeCheckpoint("training produced no periodic GRU checkpoints")
    rows = []
    for path in checkpoint_paths:
        composite.policy.load_state_dict(torch.load(path, map_location=device,
                                                    weights_only=True))
        result = evaluate_gru(model_path, composite, device=device, seed=seed,
                              episodes=eval_episodes, max_steps=max_steps, dt=dt)
        rows.append({"checkpoint": path.name, **result})
    ranked = sorted((row for row in rows if row["evaluation_errors"] == 0),
                    key=lambda row: (row["safety_violation_episodes"],
                                     row["task_errors"], row["shield_override_rate"],
                                     row["checkpoint"]))
    safe = [row for row in ranked if row["safety_violation_episodes"] == 0]
    report = {
        "selection_rule": "fewest safety violations, then fewest unsuccessful episodes, "
                          "then lowest shield override rate; publish only with zero safety violations",
        "checkpoints": rows,
        "ranked_checkpoints": [row["checkpoint"] for row in ranked],
        "selected": safe[0] if safe else None,
    }
    report_path = out_dir / "checkpoint_selection.json"
    if not safe:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise NoSafeCheckpoint("no zero-violation GRU checkpoint; no final model written")

    winner = checkpoint_dir / safe[0]["checkpoint"]
    composite.policy.load_state_dict(torch.load(winner, map_location=device,
                                                weights_only=True))
    holdout = evaluate_gru(model_path, composite, device=device, seed=seed + 10_000,
                           episodes=test_episodes, max_steps=max_steps, dt=dt)
    report["held_out_test"] = holdout
    if holdout["safety_violation_episodes"] or holdout["evaluation_errors"]:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        raise NoSafeCheckpoint("selected checkpoint failed held-out safety check; "
                               "no final model written")

    final_dir = out_dir / "final"
    final_dir.mkdir(exist_ok=True)
    final_path = final_dir / "policy.pt"
    shutil.copyfile(winner, final_path)
    report["final_model"] = str(final_path.resolve())
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
