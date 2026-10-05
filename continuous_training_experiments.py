#!/usr/bin/env python3
"""Run short continuous-action GRU experiments under four shield semantics."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
import torch


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "rl"))

from continuous_env import ContinuousSysMLEnv  # noqa: E402
from continuous_model import (  # noqa: E402
    ContinuousRecurrentActorCritic,
    select_torch_device,
)
from continuous_ppo import (  # noqa: E402
    ContinuousEpisodeBuffer,
    ContinuousRecurrentPPO,
)
from continuous_spec import ExactContinuousShield  # noqa: E402
from continuous_training_modes import (  # noqa: E402
    TRAINING_MODES,
    training_reward,
)


MODEL = ROOT / "sysml-models" / "rotary-inverted-pendulum" / "model.sysml"


def _episode(env, model, shield, mode, device, *, greedy,
             penalty_cap, action_error_scale):
    observation = env.reset()
    hidden = model.initial_hidden(1).to(device)
    trajectory = {
        "observations": [], "actions": [], "rewards": [],
        "values": [], "log_prob": [], "dones": [],
    }
    stats = {
        "reward": 0.0, "steps": 0, "unsafe_executed_steps": 0,
        "shield_interventions": 0, "absolute_correction": 0.0,
        "success": False, "truncated": False, "error": None,
    }
    done = False
    while not done:
        tensor = torch.as_tensor(
            observation, dtype=torch.float32, device=device).unsqueeze(0)
        with torch.no_grad():
            distribution, value, hidden = model(tensor, hidden)
            proposed_tensor = (distribution.mean if greedy
                               else distribution.sample())
        proposed = float(proposed_tensor.reshape(-1)[0].item())
        required = shield.required_action(env.raw_model_inputs)
        correction = abs(proposed - required)
        intervened = correction > shield.comparison_abs_tol
        executed = required if mode.use_shield else proposed
        credited = executed if mode.credit_action == "executed" else proposed
        credited_tensor = torch.as_tensor(
            [[credited]], dtype=torch.float32, device=device)
        log_probability = float(
            distribution.log_prob(credited_tensor).reshape(-1)[0].item())
        next_observation, environment_reward, done, info = env.step([executed])
        reward = training_reward(
            mode, environment_reward, correction,
            comparison_abs_tol=shield.comparison_abs_tol,
            penalty_cap=penalty_cap,
            action_error_scale=action_error_scale)
        trajectory["observations"].append(observation)
        trajectory["actions"].append([credited])
        trajectory["rewards"].append(reward)
        trajectory["values"].append(float(value.reshape(-1)[0].item()))
        trajectory["log_prob"].append(log_probability)
        trajectory["dones"].append(done)
        stats["reward"] += reward
        stats["steps"] += 1
        stats["unsafe_executed_steps"] += int(info["unsafe_executed"])
        stats["shield_interventions"] += int(mode.use_shield and intervened)
        stats["absolute_correction"] += correction
        stats["success"] = info["outcome"] == "SUCCESS"
        stats["truncated"] = bool(info["truncated"])
        if info["outcome"] == "ERROR":
            stats["error"] = info["error"] or str(info["evaluation_errors"])
            done = True
        observation = next_observation
    return trajectory, stats


def _summarize(rows):
    steps = sum(row["steps"] for row in rows)
    return {
        "episodes": len(rows),
        "successes": sum(row["success"] for row in rows),
        "truncations": sum(row["truncated"] for row in rows),
        "episodes_with_unsafe_execution": sum(
            row["unsafe_executed_steps"] > 0 for row in rows),
        "unsafe_executed_steps": sum(
            row["unsafe_executed_steps"] for row in rows),
        "shield_interventions": sum(row["shield_interventions"] for row in rows),
        "total_steps": steps,
        "mean_episode_reward": float(np.mean([row["reward"] for row in rows])),
        "mean_episode_steps": float(np.mean([row["steps"] for row in rows])),
        "mean_absolute_proposal_error": (
            sum(row["absolute_correction"] for row in rows) / max(steps, 1)),
        "errors": [row["error"] for row in rows if row["error"]],
    }


def run_mode(model_path, out_dir, initial_state, mode, *,
             observation_dimension, action_dimension, device, seed,
             episodes, episodes_per_update, evaluation_episodes, max_steps,
             penalty_cap, action_error_scale, dt):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    shield = ExactContinuousShield(str(model_path))
    policy = ContinuousRecurrentActorCritic(
        obs_dim=observation_dimension, action_dim=action_dimension,
        hidden_dim=64).to(device)
    policy.load_state_dict(initial_state)
    optimizer = ContinuousRecurrentPPO(policy, device=device)
    environment = ContinuousSysMLEnv(
        str(model_path), dt=dt, max_steps=max_steps, phase=2, rng_seed=seed,
        terminate_on_violation=mode.terminate_on_unsafe_execution,
        violation_penalty=0.01)
    buffer = ContinuousEpisodeBuffer()
    history = []
    try:
        for number in range(1, episodes + 1):
            trajectory, stats = _episode(
                environment, policy, shield, mode, device, greedy=False,
                penalty_cap=penalty_cap,
                action_error_scale=action_error_scale)
            if stats["error"]:
                raise RuntimeError(stats["error"])
            buffer.add(trajectory)
            history.append(stats)
            if number % episodes_per_update == 0 or number == episodes:
                losses = optimizer.update(buffer)
                buffer.clear()
                recent = _summarize(history[-episodes_per_update:])
                print(
                    f"[{mode.name}] {number}/{episodes} "
                    f"success={recent['successes']}/{recent['episodes']} "
                    f"unsafe_eps={recent['episodes_with_unsafe_execution']} "
                    f"reward={recent['mean_episode_reward']:.3f} "
                    f"error={recent['mean_absolute_proposal_error']:.3f} "
                    f"policy_loss={losses['policy_loss']:.4f}", flush=True)
    finally:
        environment.close()

    evaluation_environment = ContinuousSysMLEnv(
        str(model_path), dt=dt, max_steps=max_steps, phase=2,
        rng_seed=seed + 10_000,
        terminate_on_violation=mode.terminate_on_unsafe_execution,
        violation_penalty=0.01)
    evaluation = []
    try:
        for _ in range(evaluation_episodes):
            _trajectory, stats = _episode(
                evaluation_environment, policy, shield, mode, device,
                greedy=True, penalty_cap=penalty_cap,
                action_error_scale=action_error_scale)
            evaluation.append(stats)
    finally:
        evaluation_environment.close()

    out_dir.mkdir(parents=True, exist_ok=False)
    checkpoint = out_dir / "experimental_policy.pt"
    torch.save(policy.state_dict(), checkpoint)
    result = {
        "mode": mode.name,
        "use_shield": mode.use_shield,
        "credit_action": mode.credit_action,
        "terminate_on_unsafe_execution": mode.terminate_on_unsafe_execution,
        "training": _summarize(history),
        "evaluation": _summarize(evaluation),
        "checkpoint": str(checkpoint.resolve()),
        "deployable": False,
    }
    (out_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--episodes-per-update", type=int, default=10)
    parser.add_argument("--evaluation-episodes", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=3000)
    parser.add_argument("--dt", type=float, default=0.001)
    parser.add_argument("--penalty-cap", type=float, default=1.0)
    parser.add_argument("--action-error-scale", type=float, default=10.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if min(args.episodes, args.episodes_per_update,
           args.evaluation_episodes, args.max_steps) <= 0:
        parser.error("episode and step counts must be positive")
    if args.penalty_cap <= 0.0:
        parser.error("penalty cap must be positive")

    device = select_torch_device(args.device)
    shield = ExactContinuousShield(str(args.model.resolve()))
    probe = ContinuousSysMLEnv(
        str(args.model.resolve()), dt=args.dt, max_steps=args.max_steps,
        phase=1, rng_seed=args.seed)
    try:
        observation_dimension = probe.obs_dim
        action_dimension = probe.action_dim
    finally:
        probe.close()
    if action_dimension != 1:
        parser.error(
            "this preliminary comparison requires one continuous action")
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    initial = ContinuousRecurrentActorCritic(
        obs_dim=observation_dimension, action_dim=action_dimension,
        hidden_dim=64)
    initial_state = deepcopy(initial.state_dict())
    args.output.mkdir(parents=True)
    results = []
    for mode in TRAINING_MODES:
        results.append(run_mode(
            args.model.resolve(), args.output / mode.name,
            initial_state, mode,
            observation_dimension=observation_dimension,
            action_dimension=action_dimension,
            device=device, seed=args.seed,
            episodes=args.episodes,
            episodes_per_update=args.episodes_per_update,
            evaluation_episodes=args.evaluation_episodes,
            max_steps=args.max_steps,
            penalty_cap=args.penalty_cap,
            action_error_scale=args.action_error_scale,
            dt=args.dt))
    report = {
        "schema": "clarity.continuous-training-comparison.v1",
        "source_model": str(args.model.resolve()),
        "source_model_sha256": hashlib.sha256(
            args.model.read_bytes()).hexdigest(),
        "device": str(device),
        "seed": args.seed,
        "episodes_per_mode": args.episodes,
        "evaluation_episodes_per_mode": args.evaluation_episodes,
        "max_steps": args.max_steps,
        "proposal_penalty_cap": args.penalty_cap,
        "action_error_scale": args.action_error_scale,
        "observation_dimension": observation_dimension,
        "action_dimension": action_dimension,
        "common_initial_weights": True,
        "experimental_only": True,
        "results": results,
    }
    (args.output / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
