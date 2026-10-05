#!/usr/bin/env python3
"""Compare compact GRU training improvements for the pendulum controller."""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import torch
import torch.nn as nn


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "rl"))
sys.path.insert(0, str(ROOT / "sysml-models"))

from continuous_env import ContinuousSysMLEnv  # noqa: E402
from continuous_gru import generate_oracle_data  # noqa: E402
from continuous_model import (  # noqa: E402
    BoundedMeanContinuousRecurrentActorCritic,
    ContinuousFeedForwardActorCritic,
    ContinuousRecurrentActorCritic,
    select_torch_device,
)
from continuous_ppo import (  # noqa: E402
    ContinuousEpisodeBuffer,
    ContinuousRecurrentPPO,
)
from continuous_spec import ExactContinuousShield  # noqa: E402
from continuous_training_experiments import _episode, _summarize  # noqa: E402
from continuous_training_modes import TRAINING_MODES  # noqa: E402
from execution_parameters import load_execution_parameters  # noqa: E402


MODEL = ROOT / "sysml-models" / "rotary-inverted-pendulum" / "model.sysml"


def _mode(name):
    return next(row for row in TRAINING_MODES if row.name == name)


def _make_policy(kind, obs_dim, action_dim, initial_state, device,
                 standard_deviation):
    policy_types = {
        "standard": ContinuousRecurrentActorCritic,
        "bounded": BoundedMeanContinuousRecurrentActorCritic,
        "feedforward": ContinuousFeedForwardActorCritic,
    }
    policy_type = policy_types[kind]
    policy = policy_type(
        obs_dim=obs_dim, action_dim=action_dim, hidden_dim=64).to(device)
    if initial_state is not None:
        policy.load_state_dict(initial_state)
    with torch.no_grad():
        policy.action_log_std.fill_(math.log(standard_deviation))
    return policy


def _clone(policy, observations, actions, *, device, epochs, loss_kind,
           batch_size=512, learning_rate=1e-3, seed=42):
    optimizer = torch.optim.Adam(policy.parameters(), lr=learning_rate)
    criterion = nn.MSELoss() if loss_kind == "mse" else nn.HuberLoss()
    rng = np.random.default_rng(seed)
    history = []
    policy.train()
    for epoch in range(1, epochs + 1):
        order = rng.permutation(len(observations))
        total = 0.0
        for start in range(0, len(order), batch_size):
            indices = order[start:start + batch_size]
            batch_observation = torch.as_tensor(
                observations[indices], dtype=torch.float32, device=device)
            batch_action = torch.as_tensor(
                actions[indices], dtype=torch.float32, device=device)
            hidden = policy.initial_hidden(len(indices)).to(device)
            distribution, _value, _hidden = policy(
                batch_observation, hidden)
            loss = criterion(distribution.mean, batch_action)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
            optimizer.step()
            total += loss.item() * len(indices)
        history.append(total / len(observations))
    return history


def _ppo(policy, model_path, shield, mode, *, device, episodes,
         episodes_per_update, max_steps, seed, penalty_cap,
         action_error_scale, time_budget, override_budget, dt):
    environment = ContinuousSysMLEnv(
        str(model_path), dt=dt, max_steps=max_steps, phase=2,
        rng_seed=seed, terminate_on_violation=mode.terminate_on_prohibition,
        violation_penalty=0.0,
        terminating_metadata=frozenset({"Prohibition"}))
    trainer = ContinuousRecurrentPPO(
        policy, device=device, learning_rate=1e-4, entropy=0.0)
    buffer = ContinuousEpisodeBuffer()
    rows = []
    try:
        for number in range(1, episodes + 1):
            trajectory, stats = _episode(
                environment, policy, shield, mode, device, greedy=False,
                penalty_cap=penalty_cap,
                action_error_scale=action_error_scale,
                max_steps=max_steps,
                time_budget=time_budget,
                override_budget=override_budget)
            if stats["error"]:
                raise RuntimeError(stats["error"])
            buffer.add(trajectory)
            rows.append(stats)
            if number % episodes_per_update == 0 or number == episodes:
                trainer.update(buffer)
                buffer.clear()
    finally:
        environment.close()
    return _summarize(rows)


def _evaluate(policy, model_path, shield, mode, *, device, episodes,
              max_steps, seed, penalty_cap, action_error_scale,
              time_budget, override_budget, dt):
    environment = ContinuousSysMLEnv(
        str(model_path), dt=dt, max_steps=max_steps, phase=2,
        rng_seed=seed, terminate_on_violation=mode.terminate_on_prohibition,
        violation_penalty=0.0,
        terminating_metadata=frozenset({"Prohibition"}))
    rows = []
    policy.eval()
    try:
        for _ in range(episodes):
            _trajectory, stats = _episode(
                environment, policy, shield, mode, device, greedy=True,
                penalty_cap=penalty_cap,
                action_error_scale=action_error_scale,
                max_steps=max_steps,
                time_budget=time_budget,
                override_budget=override_budget)
            rows.append(stats)
    finally:
        environment.close()
        policy.train()
    return _summarize(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--oracle-samples", type=int, default=3000)
    parser.add_argument("--clone-epochs", type=int, default=30)
    parser.add_argument("--ppo-episodes", type=int, default=20)
    parser.add_argument("--evaluation-episodes", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=6000)
    parser.add_argument(
        "--dt", type=float, default=None,
        help="compatibility assertion; must equal the source-derived integration step")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if min(args.oracle_samples, args.clone_epochs, args.ppo_episodes,
           args.evaluation_episodes, args.max_steps) <= 0:
        parser.error("all count arguments must be positive")

    model_path = args.model.resolve()
    execution = load_execution_parameters(model_path)
    dt = (execution.integration_step_float if args.dt is None else
          execution.require_matching_integration_step(args.dt))
    device = select_torch_device(args.device)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    shield = ExactContinuousShield(str(model_path))
    probe = ContinuousSysMLEnv(
        str(model_path), dt=dt, max_steps=args.max_steps,
        phase=1, rng_seed=args.seed)
    try:
        obs_dim, action_dim = probe.obs_dim, probe.action_dim
        observations, actions = generate_oracle_data(
            probe, shield, args.oracle_samples, max_steps=args.max_steps)
    finally:
        probe.close()

    seed_policy = ContinuousRecurrentActorCritic(
        obs_dim=obs_dim, action_dim=action_dim, hidden_dim=64)
    initial_state = deepcopy(seed_policy.state_dict())
    candidates = (
        ("bc_mse", "standard", "mse", 1.0, None, True),
        ("bc_huber_low_std", "standard", "huber", 0.10, None, True),
        ("bc_huber_bounded", "bounded", "huber", 0.10, None, True),
        ("bc_huber_shielded_ppo", "standard", "huber", 0.10,
         "shielded_proposal_credit", True),
        ("bc_huber_bounded_unshielded_ppo", "bounded", "huber", 0.10,
         "unshielded_safety_terminate", True),
        ("feedforward_shielded_ppo_from_scratch", "feedforward", None,
         1.0, "shielded_proposal_credit", False),
    )
    args.output.mkdir(parents=True)
    results = []
    reward = {
        "penalty_cap": 1.0, "action_error_scale": 10.0,
        "time_budget": 0.10, "override_budget": 0.05,
    }
    for index, (name, kind, loss_kind, std, fine_tune,
                clone_first) in enumerate(candidates):
        print(f"[{index + 1}/{len(candidates)}] {name}", flush=True)
        if kind == "feedforward":
            torch.manual_seed(args.seed)
        policy = _make_policy(
            kind, obs_dim, action_dim,
            initial_state if kind != "feedforward" else None, device, std)
        history = None
        if clone_first:
            history = _clone(
                policy, observations, actions, device=device,
                epochs=args.clone_epochs, loss_kind=loss_kind, seed=args.seed)
        fine_tuning = None
        if fine_tune is not None:
            fine_tuning = _ppo(
                policy, model_path, shield, _mode(fine_tune),
                device=device, episodes=args.ppo_episodes,
                episodes_per_update=5, max_steps=args.max_steps,
                seed=args.seed + 1000, dt=dt, **reward)
        shielded = _evaluate(
            policy, model_path, shield, _mode("shielded_proposal_credit"),
            device=device, episodes=args.evaluation_episodes,
            max_steps=args.max_steps, seed=args.seed + 20_000,
            dt=dt, **reward)
        unshielded = _evaluate(
            policy, model_path, shield, _mode("unshielded_safety_terminate"),
            device=device, episodes=args.evaluation_episodes,
            max_steps=args.max_steps, seed=args.seed + 20_000,
            dt=dt, **reward)
        candidate_dir = args.output / name
        candidate_dir.mkdir()
        checkpoint = candidate_dir / "experimental_policy.pt"
        torch.save(policy.state_dict(), checkpoint)
        row = {
            "name": name,
            "policy_kind": kind,
            "clone_loss": loss_kind,
            "clone_first": clone_first,
            "proposal_standard_deviation": std,
            "clone_initial_loss": history[0] if history else None,
            "clone_final_loss": history[-1] if history else None,
            "fine_tune_mode": fine_tune,
            "fine_tuning": fine_tuning,
            "shielded_evaluation": shielded,
            "unshielded_evaluation": unshielded,
            "checkpoint": str(checkpoint.resolve()),
            "deployable": False,
        }
        (candidate_dir / "result.json").write_text(
            json.dumps(row, indent=2, sort_keys=True) + "\n")
        results.append(row)
        print(json.dumps({
            "candidate": name,
            "clone_final_loss": history[-1] if history else None,
            "shielded_error": shielded["mean_absolute_proposal_error"],
            "unshielded_successes": unshielded["successes"],
            "unshielded_unsafe_episodes": (
                unshielded["episodes_with_unsafe_execution"]),
        }, sort_keys=True), flush=True)

    report = {
        "schema": "clarity.continuous-improvement-battery.v1",
        "source_model_sha256": hashlib.sha256(
            model_path.read_bytes()).hexdigest(),
        "device": str(device),
        "seed": args.seed,
        "oracle_samples": args.oracle_samples,
        "clone_epochs": args.clone_epochs,
        "ppo_episodes": args.ppo_episodes,
        "evaluation_episodes": args.evaluation_episodes,
        "max_steps": args.max_steps,
        "execution_parameters": execution.as_dict(),
        "common_initial_weights_for_recurrent_candidates": True,
        "feedforward_candidate_initialized_from_same_seed": True,
        "common_oracle_data": True,
        "experimental_only": True,
        "results": results,
    }
    (args.output / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print("IMPROVEMENT_BATTERY")
    for row in results:
        print(json.dumps({
            "name": row["name"],
            "clone_final_loss": row["clone_final_loss"],
            "shielded_error": row["shielded_evaluation"][
                "mean_absolute_proposal_error"],
            "shielded_successes": row["shielded_evaluation"]["successes"],
            "unshielded_error": row["unshielded_evaluation"][
                "mean_absolute_proposal_error"],
            "unshielded_successes": row["unshielded_evaluation"]["successes"],
            "unshielded_unsafe_episodes": row["unshielded_evaluation"][
                "episodes_with_unsafe_execution"],
        }, sort_keys=True))


if __name__ == "__main__":
    main()
