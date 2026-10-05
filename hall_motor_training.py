#!/usr/bin/env python3
"""Train the two shielded PPO modes for the Hall-sensored BLDC model."""

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
sys.path.insert(0, str(ROOT / "sysml-models"))

from continuous_env import ContinuousSysMLEnv  # noqa: E402
from continuous_model import (  # noqa: E402
    ContinuousRecurrentActorCritic,
    select_torch_device,
)
from continuous_training_experiments import run_mode  # noqa: E402
from continuous_training_modes import TRAINING_MODES  # noqa: E402
from hall_motor_shield import HallMotorProjectionShield  # noqa: E402
from hall_motor_verification import (  # noqa: E402
    certify_structure,
    compile_contract,
)
from execution_parameters import load_execution_parameters  # noqa: E402


MODEL = ROOT / "sysml-models" / "hall-sensored-bldc" / "model.sysml"
SHIELDED_MODES = tuple(mode for mode in TRAINING_MODES if mode.use_shield)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--episodes", type=int, default=100)
    parser.add_argument("--episodes-per-update", type=int, default=10)
    parser.add_argument("--evaluation-episodes", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=3000)
    parser.add_argument("--penalty-cap", type=float, default=1.0)
    parser.add_argument("--action-error-scale", type=float, default=10.0)
    parser.add_argument("--time-budget", type=float, default=0.10)
    parser.add_argument("--override-budget", type=float, default=0.05)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    if min(args.episodes, args.episodes_per_update,
           args.evaluation_episodes, args.max_steps) <= 0:
        parser.error("episode and step counts must be positive")
    if args.episodes_per_update > args.episodes:
        parser.error("episodes-per-update cannot exceed episodes")

    model_path = args.model.resolve()
    execution = load_execution_parameters(model_path)
    dt = execution.integration_step_float
    # Training is downstream of the cheap structural gate.  Refuse to spend
    # compute on a model whose recognized safety transition is inconsistent.
    contract = compile_contract(model_path)
    preflight = certify_structure(contract)
    if not preflight["proved"]:
        parser.error("Hall-motor structural safety preflight did not prove")
    device = select_torch_device(args.device)
    shield = HallMotorProjectionShield(model_path)
    observation_scales = {
        "estimatedMechanicalSpeedRadiansPerSecond":
            contract.maximum_speed_radians_per_second,
        "sampledPairCurrentAmperes": contract.current_limit_amperes,
        "hallCode": 6.0,
        "targetMechanicalSpeedRadiansPerSecond":
            contract.maximum_target_radians_per_second,
    }
    probe = ContinuousSysMLEnv(
        str(model_path), dt=dt, max_steps=args.max_steps,
        phase=1, rng_seed=args.seed,
        observation_scales=observation_scales)
    try:
        observation_dimension = probe.obs_dim
        action_dimension = probe.action_dim
        observation_keys = list(getattr(probe, "_obs_keys", ()))
        observation_scale = getattr(probe, "_obs_scale", None)
    finally:
        probe.close()
    if action_dimension != 1:
        parser.error("motor experiment requires one continuous action")

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    initial = ContinuousRecurrentActorCritic(
        obs_dim=observation_dimension, action_dim=action_dimension,
        hidden_dim=64)
    initial_state = deepcopy(initial.state_dict())

    args.output.mkdir(parents=True)
    results = []
    for mode in SHIELDED_MODES:
        results.append(run_mode(
            model_path, args.output / mode.name, initial_state, mode,
            shield=shield,
            observation_dimension=observation_dimension,
            action_dimension=action_dimension,
            device=device,
            seed=args.seed,
            episodes=args.episodes,
            episodes_per_update=args.episodes_per_update,
            evaluation_episodes=args.evaluation_episodes,
            max_steps=args.max_steps,
            penalty_cap=args.penalty_cap,
            action_error_scale=args.action_error_scale,
            time_budget=args.time_budget,
            override_budget=args.override_budget,
            dt=dt,
            observation_scales=observation_scales,
            executed_action_state_key=(
                "system::drive::executedSignedDutyFraction"
            ),
        ))

    report = {
        "schema": "clarity.hall-motor-shielded-ppo.v1",
        "source_model": str(model_path),
        "source_model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "device": str(device),
        "seed": args.seed,
        "episodes_per_mode": args.episodes,
        "evaluation_episodes_per_mode": args.evaluation_episodes,
        "max_steps": args.max_steps,
        "execution_parameters": execution.as_dict(),
        "integration_step_seconds": dt,
        "proposal_penalty_cap": args.penalty_cap,
        "time_penalty_budget": args.time_budget,
        "override_penalty_budget": args.override_budget,
        "action_error_scale": args.action_error_scale,
        "observation_scale": observation_scale,
        "observation_keys": observation_keys,
        "observation_dimension": observation_dimension,
        "action_dimension": action_dimension,
        "shield": shield.report(),
        "structural_safety_preflight": preflight,
        "common_initial_weights": True,
        "experimental_only": True,
        "results": results,
    }
    (args.output / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
