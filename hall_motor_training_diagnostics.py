#!/usr/bin/env python3
"""Short PPO ablations for diagnosing Hall-motor training behavior.

This is an experimental diagnostic, not a deployable training entry point.
Every configuration uses the mathematically correct on-policy proposal
likelihood.  The remaining ablations compare exploration, reward shape, and
target randomization without reintroducing the invalid executed-action PPO
accounting that this diagnostic exposed.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import torch


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "rl"))
sys.path.insert(0, str(ROOT / "sysml-models"))

from continuous_env import ContinuousSysMLEnv  # noqa: E402
from continuous_model import (  # noqa: E402
    BoundedMeanContinuousRecurrentActorCritic,
    ContinuousRecurrentActorCritic,
    select_torch_device,
)
from continuous_ppo import ContinuousEpisodeBuffer, ContinuousRecurrentPPO  # noqa: E402
from continuous_training_modes import TRAINING_MODES, training_reward  # noqa: E402
from hall_motor_shield import HallMotorProjectionShield  # noqa: E402
from hall_motor_verification import compile_contract  # noqa: E402
from execution_parameters import load_execution_parameters  # noqa: E402


MODEL = ROOT / "sysml-models" / "hall-sensored-bldc" / "model.sysml"
FIXED_TARGET = 314.159265358979
EXECUTED_MODE = next(
    mode for mode in TRAINING_MODES
    if mode.name == "shielded_executed_credit")


CONFIGURATIONS = (
    {
        "name": "unbounded_fixed_sparse",
        "bounded": False,
        "reward": "sparse",
        "fixed_target": True,
    },
    {
        "name": "on_policy_fixed_sparse",
        "bounded": False,
        "reward": "sparse",
        "fixed_target": True,
    },
    {
        "name": "bounded_fixed_sparse",
        "bounded": True,
        "reward": "sparse",
        "fixed_target": True,
    },
    {
        "name": "bounded_fixed_progress",
        "bounded": True,
        "reward": "progress",
        "fixed_target": True,
    },
    {
        "name": "bounded_random_progress",
        "bounded": True,
        "reward": "progress",
        "fixed_target": False,
    },
)


def _fix_target(environment, target: float) -> None:
    matches = 0
    for qualified_name, bounds in environment._scenario_inputs.items():
        if qualified_name.endswith("targetMechanicalSpeedRadiansPerSecond"):
            bounds["lower"] = target
            bounds["upper"] = target
            bounds["default"] = target
            matches += 1
    if matches != 1:
        raise RuntimeError(f"expected one motor target scenario input, found {matches}")


def _environment(model: Path, *, seed: int, max_steps: int,
                 fixed_target: bool, dt: float):
    contract = compile_contract(model)
    environment = ContinuousSysMLEnv(
        str(model), dt=dt, max_steps=max_steps, phase=2,
        rng_seed=seed, terminate_on_violation=False, violation_penalty=0.0,
        terminating_metadata=frozenset({"Prohibition"}),
        observation_scales={
            "estimatedMechanicalSpeedRadiansPerSecond":
                contract.maximum_speed_radians_per_second,
            "sampledPairCurrentAmperes": contract.current_limit_amperes,
            "hallCode": 6.0,
            "targetMechanicalSpeedRadiansPerSecond":
                contract.maximum_target_radians_per_second,
        })
    if fixed_target:
        _fix_target(environment, FIXED_TARGET)
    return environment


def _episode(environment, policy, shield, device, config, *, max_steps: int,
             greedy: bool):
    observation = environment.reset()
    hidden = policy.initial_hidden(1).to(device)
    trajectory = {
        "observations": [], "actions": [], "rewards": [],
        "values": [], "log_prob": [], "dones": [],
    }
    stats = {
        "success": False,
        "truncated": False,
        "unsafe_steps": 0,
        "interventions": 0,
        "steps": 0,
        "reward": 0.0,
        "absolute_correction": 0.0,
    }
    done = False
    while not done:
        before = environment.raw_model_inputs
        old_error = abs(
            float(before["targetMechanicalSpeedRadiansPerSecond"])
            - float(before["estimatedMechanicalSpeedRadiansPerSecond"]))
        tensor = torch.as_tensor(
            observation, dtype=torch.float32, device=device).unsqueeze(0)
        with torch.no_grad():
            distribution, value, hidden = policy(tensor, hidden)
            sample = distribution.mean if greedy else distribution.sample()
        proposal = float(sample.reshape(-1)[0].item())
        executed, intervened, correction = shield.select(proposal, before)
        next_observation, environment_reward, done, info = environment.step(
            [executed])
        process_action = float(info["state"][
            "system::drive::executedSignedDutyFraction"
        ])
        correction = abs(proposal - process_action)
        intervened = correction > shield.comparison_abs_tol

        if config["reward"] == "progress" and not done:
            after = environment.raw_model_inputs
            new_error = abs(
                float(after["targetMechanicalSpeedRadiansPerSecond"])
                - float(after["estimatedMechanicalSpeedRadiansPerSecond"]))
            scale = max(
                abs(float(after["targetMechanicalSpeedRadiansPerSecond"])),
                1.0,
            )
            reward = (old_error - new_error) / scale - 0.10 / max_steps
        elif config["reward"] == "progress" and info["outcome"] == "SUCCESS":
            reward = 1.0
        else:
            reward = training_reward(
                EXECUTED_MODE, environment_reward, correction,
                comparison_abs_tol=shield.comparison_abs_tol,
                penalty_cap=1.0, action_error_scale=10.0,
                max_steps=max_steps, time_budget=0.10,
                override_budget=0.05)

        log_probability = float(
            distribution.log_prob(sample).reshape(-1)[0].item())
        trajectory["observations"].append(observation)
        trajectory["actions"].append([proposal])
        trajectory["rewards"].append(float(reward))
        trajectory["values"].append(float(value.reshape(-1)[0].item()))
        trajectory["log_prob"].append(log_probability)
        trajectory["dones"].append(done)

        stats["success"] = info["outcome"] == "SUCCESS"
        stats["truncated"] = bool(info["truncated"])
        stats["unsafe_steps"] += int(info["unsafe_executed"])
        stats["interventions"] += int(intervened)
        stats["steps"] += 1
        stats["reward"] += float(reward)
        stats["absolute_correction"] += correction
        observation = next_observation
    return trajectory, stats


def _summary(rows: list[dict]) -> dict:
    steps = sum(row["steps"] for row in rows)
    return {
        "episodes": len(rows),
        "successes": sum(row["success"] for row in rows),
        "truncations": sum(row["truncated"] for row in rows),
        "unsafe_steps": sum(row["unsafe_steps"] for row in rows),
        "interventions": sum(row["interventions"] for row in rows),
        "intervention_rate": (
            sum(row["interventions"] for row in rows) / max(steps, 1)),
        "mean_steps": float(np.mean([row["steps"] for row in rows])),
        "mean_reward": float(np.mean([row["reward"] for row in rows])),
        "mean_absolute_correction": (
            sum(row["absolute_correction"] for row in rows) / max(steps, 1)),
    }


def run_configuration(config, model_path: Path, *, device, seed: int,
                      episodes: int, evaluation_episodes: int,
                      max_steps: int, observation_dimension: int,
                      dt: float) -> dict:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if config["bounded"]:
        policy = BoundedMeanContinuousRecurrentActorCritic(
            obs_dim=observation_dimension, action_dim=1, hidden_dim=64,
            action_limit=1.0).to(device)
        with torch.no_grad():
            policy.action_log_std.fill_(math.log(0.20))
    else:
        policy = ContinuousRecurrentActorCritic(
            obs_dim=observation_dimension, action_dim=1,
            hidden_dim=64).to(device)
    optimizer = ContinuousRecurrentPPO(policy, device=device)
    shield = HallMotorProjectionShield(model_path)
    environment = _environment(
        model_path, seed=seed, max_steps=max_steps,
        fixed_target=config["fixed_target"], dt=dt)
    buffer = ContinuousEpisodeBuffer()
    training = []
    try:
        for number in range(1, episodes + 1):
            trajectory, stats = _episode(
                environment, policy, shield, device, config,
                max_steps=max_steps, greedy=False)
            buffer.add(trajectory)
            training.append(stats)
            if number % 5 == 0 or number == episodes:
                optimizer.update(buffer)
                buffer.clear()
    finally:
        environment.close()

    evaluation_environment = _environment(
        model_path, seed=seed + 10_000, max_steps=max_steps,
        fixed_target=config["fixed_target"], dt=dt)
    evaluation = []
    try:
        for _ in range(evaluation_episodes):
            _trajectory, stats = _episode(
                evaluation_environment, policy, shield, device, config,
                max_steps=max_steps, greedy=True)
            evaluation.append(stats)
    finally:
        evaluation_environment.close()
    result = {
        "configuration": config,
        "training": _summary(training),
        "evaluation": _summary(evaluation),
    }
    print(json.dumps(result, sort_keys=True), flush=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--evaluation-episodes", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    model_path = args.model.resolve()
    execution = load_execution_parameters(model_path)
    dt = execution.integration_step_float
    device = select_torch_device(args.device)
    probe = _environment(
        model_path, seed=args.seed, max_steps=args.max_steps,
        fixed_target=True, dt=dt)
    try:
        observation_dimension = probe.obs_dim
    finally:
        probe.close()
    results = [
        run_configuration(
            config, model_path, device=device, seed=args.seed,
            episodes=args.episodes,
            evaluation_episodes=args.evaluation_episodes,
            max_steps=args.max_steps,
            observation_dimension=observation_dimension, dt=dt)
        for config in CONFIGURATIONS
    ]
    args.output.mkdir(parents=True)
    report = {
        "schema": "clarity.hall-motor-training-diagnostic.v1",
        "experimental_only": True,
        "device": str(device),
        "episodes": args.episodes,
        "evaluation_episodes": args.evaluation_episodes,
        "max_steps": args.max_steps,
        "execution_parameters": execution.as_dict(),
        "results": results,
    }
    (args.output / "diagnostic.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
