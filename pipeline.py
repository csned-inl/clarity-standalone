#!/usr/bin/env python3
"""Standalone SysML v2 → SMV proof → shield → policy pipeline."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sysml-models"))
sys.path.insert(0, str(ROOT / "rl"))

from analytic import evaluate, fit, save  # noqa: E402
from execution_parameters import load_execution_parameters  # noqa: E402
from formal import verify  # noqa: E402
from gru import train_and_select  # noqa: E402
from shield import SpecShield  # noqa: E402

MODELS = {
    "thermostat": ROOT / "sysml-models" / "thermostat" / "model.sysml",
    "cruise": ROOT / "sysml-models" / "cruise-controller-model" / "model.sysml",
    "mixing": ROOT / "sysml-models" / "mixing-sysml-model" / "model.sysml",
}
def run_one(model_name: str, mode: str, output_root: Path, *, nuxmv: Path,
            timeout: int, seed: int, max_steps: int, eval_episodes: int,
            test_episodes: int, oracle_samples: int, oracle_epochs: int,
    ppo_episodes: int) -> dict:
    model = MODELS[model_name]
    execution = load_execution_parameters(model)
    dt = execution.integration_step_float
    out_dir = output_root / model_name / mode
    if out_dir.exists():
        raise FileExistsError(f"run directory already exists: {out_dir}")
    out_dir.mkdir(parents=True)

    proof = verify(model, out_dir / "formal", dt=dt,
                   nuxmv=nuxmv, timeout_seconds=timeout)
    shield = SpecShield(str(model))
    shield_report = {
        "action_count": len(shield.action_map),
        "dead_actions": sorted(shield.dead_actions),
        "valid_actions": len(shield.action_map) - len(shield.dead_actions),
        "input_names": shield.in_params,
        "output_names": shield.out_params,
    }
    (out_dir / "shield.json").write_text(
        json.dumps(shield_report, indent=2, sort_keys=True) + "\n")

    if mode == "analytic":
        policy = fit(model)
        result = evaluate(model, policy, episodes=test_episodes, seed=seed,
                          max_steps=max_steps, dt=dt)
        (out_dir / "analytic_evaluation.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n")
        if (result["safety_violation_episodes"] or result["evaluation_errors"]
                or result["pointwise_rule_disagreements"]):
            raise RuntimeError("analytical policy failed evaluation; no final model written")
        final_dir = out_dir / "final"
        final_dir.mkdir()
        final = final_dir / "policy.json"
        save(policy, final)
        policy_report = {"method": "analytical_affine_predicate_fit",
                         "evaluation": result,
                         "final_model": str(final.resolve())}
    else:
        policy_report = train_and_select(
            model, out_dir, seed=seed, max_steps=max_steps,
            eval_episodes=eval_episodes, test_episodes=test_episodes,
            oracle_samples=oracle_samples, oracle_epochs=oracle_epochs,
            ppo_episodes=ppo_episodes, dt=dt)

    summary = {
        "model": model_name, "method": mode,
        "dt_seconds": dt,
        "controller_interval_seconds": float(
            execution.controller_interval_seconds),
        "execution_parameters": execution.as_dict(),
        "model_sha256": proof["model_sha256"],
        "formal_verified": proof["verified"],
        "formal_report": str((out_dir / "formal" / "verification.json").resolve()),
        "shield": shield_report,
        "policy": policy_report,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=[*MODELS, "all"], default="all")
    parser.add_argument("--mode", choices=["analytic", "gru"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nuxmv", type=Path, default=shutil.which("nuXmv"))
    parser.add_argument("--timeout", type=int, default=300,
                        help="seconds allowed for each formal stage")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=1200)
    parser.add_argument("--eval-episodes", type=int, default=100)
    parser.add_argument("--test-episodes", type=int, default=100)
    parser.add_argument("--oracle-samples", type=int, default=2000)
    parser.add_argument("--oracle-epochs", type=int, default=100)
    parser.add_argument("--ppo-episodes", type=int, default=2000)
    args = parser.parse_args()
    if args.nuxmv is None or not args.nuxmv.is_file():
        parser.error("give an executable nuXmv path with --nuxmv")
    if min(args.timeout, args.max_steps, args.eval_episodes,
           args.test_episodes) <= 0:
        parser.error("timeout, max steps, and evaluation counts must be positive")

    names = list(MODELS) if args.model == "all" else [args.model]
    for name in names:
        print(f"CLARITY: {name}, {args.mode}", flush=True)
        summary = run_one(
            name, args.mode, args.output.resolve(), nuxmv=args.nuxmv,
            timeout=args.timeout, seed=args.seed, max_steps=args.max_steps,
            eval_episodes=args.eval_episodes,
            test_episodes=args.test_episodes,
            oracle_samples=args.oracle_samples,
            oracle_epochs=args.oracle_epochs,
            ppo_episodes=args.ppo_episodes)
        print(f"Final model: {summary['policy']['final_model']}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
