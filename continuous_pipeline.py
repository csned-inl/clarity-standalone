#!/usr/bin/env python3
"""Prepare and train the first continuous-action CLARITY controller path.

Preparation is VM-friendly and does not import PyTorch.  Training is a
separate opt-in stage intended for a configured CPU/CUDA/MPS runner.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "sysml-models"))
sys.path.insert(0, str(ROOT / "rl"))

from continuous_spec import ExactContinuousShield  # noqa: E402
from execution_parameters import load_execution_parameters  # noqa: E402


MODEL = ROOT / "sysml-models" / "rotary-inverted-pendulum" / "model.sysml"
EXTRACTOR = ROOT / "sysml-models" / "mc-extract.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(model: Path, out_dir: Path, *, timeout: int,
            nuxmv: Path | None = None) -> dict:
    """Extract the typed interface and SMV model; optionally run nuXmv."""
    model = model.resolve()
    execution = load_execution_parameters(model)
    dt = execution.integration_step_float
    out_dir.mkdir(parents=True, exist_ok=False)
    shield = ExactContinuousShield(str(model))
    interface = shield.report()
    interface["model"] = str(model)
    interface["model_sha256"] = _sha256(model)
    (out_dir / "continuous_interface.json").write_text(
        json.dumps(interface, indent=2, sort_keys=True) + "\n")

    formal_dir = out_dir / "formal"
    formal_dir.mkdir()
    smv = formal_dir / "model.smv"
    extraction = subprocess.run(
        [sys.executable, str(EXTRACTOR), str(model), "-o", str(smv)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    (formal_dir / "extract.log").write_text(
        extraction.stdout + extraction.stderr)
    if extraction.returncode != 0 or not smv.is_file():
        raise RuntimeError(
            f"continuous SMV extraction failed; see {formal_dir / 'extract.log'}")

    source = smv.read_text()
    output = re.escape(interface["output_name"])
    declarations = re.findall(
        rf"^\s*\w*{output}\s*:\s*(\w+)\s*;\s*$",
        source, re.MULTILINE)
    if declarations != ["real"]:
        raise RuntimeError(
            "SMV extractor did not preserve the Real neural-output type: "
            f"{declarations}")
    property_count = len(re.findall(r"^INVARSPEC\b", source, re.MULTILINE))
    if property_count == 0:
        raise RuntimeError("SMV extractor emitted no safety properties")

    formal = {
        "status": "generated_not_proved",
        "smv": str(smv.resolve()),
        "smv_sha256": _sha256(smv),
        "invariant_count": property_count,
        "verified": False,
    }
    if nuxmv is not None:
        if not nuxmv.is_file():
            raise FileNotFoundError(f"nuXmv executable not found: {nuxmv}")
        from formal import verify
        from pendulum_envelope_certificate import certify as certify_envelope
        formal = verify(
            model, formal_dir, dt=dt, nuxmv=nuxmv,
            timeout_seconds=timeout,
            obligation_certifiers={
                "Stay Within Balance Controller Envelope": certify_envelope,
            })
        formal["status"] = "proved" if formal["verified"] else "failed"

    report = {
        "model": str(model),
        "model_sha256": interface["model_sha256"],
        "execution_parameters": execution.as_dict(),
        "integration_step_seconds": dt,
        "interface": interface,
        "formal": formal,
        "training_ready": bool(formal["verified"]),
    }
    (out_dir / "preparation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nuxmv", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--train", action="store_true",
                        help="run GRU exact-feedback cloning after formal proof")
    parser.add_argument("--device", default="auto",
                        help="auto, cpu, cuda, or mps")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-steps", type=int, default=6000)
    parser.add_argument("--oracle-samples", type=int, default=2000)
    parser.add_argument("--oracle-epochs", type=int, default=100)
    parser.add_argument("--eval-episodes", type=int, default=100)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    if args.output.exists():
        parser.error(f"output directory already exists: {args.output}")
    if args.train and args.nuxmv is None:
        parser.error("training requires --nuxmv; unproved models do not train")

    run_dir = args.output.resolve()
    report = prepare(
        args.model, run_dir, timeout=args.timeout, nuxmv=args.nuxmv)
    if args.train:
        if not report["formal"]["verified"]:
            raise RuntimeError("formal proof failed; training was not started")
        from continuous_gru import train_exact_feedback_clone
        training = train_exact_feedback_clone(
            args.model.resolve(), run_dir / "gru", seed=args.seed,
            max_steps=args.max_steps, oracle_samples=args.oracle_samples,
            oracle_epochs=args.oracle_epochs,
            eval_episodes=args.eval_episodes,
            device_name=args.device)
        report["training"] = training
        (run_dir / "summary.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"Final shield-dependent model: {training['final_model']}")
    else:
        shutil.copyfile(run_dir / "preparation.json", run_dir / "summary.json")
        print(f"Prepared continuous pipeline inputs: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
