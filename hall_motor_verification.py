#!/usr/bin/env python3
"""Fail-closed safety verification for the Hall-sensored BLDC model.

The compiler deliberately slices only the controller/drive relations needed
by the declared safety requirements.  It does not encode the plant or sensor
simulator.  Source-shape checks fail closed before either certificate is
issued, so a changed relation cannot silently inherit an old proof.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from formal import verify_smv


ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "sysml-models" / "hall-sensored-bldc" / "model.sysml"

POSITIVE_TABLE = {
    6: (3, 2, 1),
    4: (3, 1, 2),
    5: (2, 1, 3),
    1: (2, 3, 1),
    3: (1, 3, 2),
    2: (1, 2, 3),
}
NEGATIVE_TABLE = {
    6: (2, 3, 1),
    2: (2, 1, 3),
    3: (3, 1, 2),
    1: (3, 2, 1),
    5: (1, 2, 3),
    4: (1, 3, 2),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(source: str, start: str, end: str) -> str:
    try:
        return source.split(start, 1)[1].split(end, 1)[0]
    except IndexError as exc:
        raise ValueError(f"required SysML section is missing: {start}") from exc


def _one_number(source: str, pattern: str, label: str) -> float:
    matches = re.findall(pattern, source, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one {label}, found {len(matches)}")
    return float(matches[0])


def _require_regex(source: str, pattern: str, label: str) -> None:
    if re.search(pattern, source, re.MULTILINE | re.DOTALL) is None:
        raise ValueError(f"unrecognized or missing {label}")


@dataclass(frozen=True)
class MotorSafetyContract:
    model: str
    model_sha256: str
    maximum_duty_magnitude: float
    configured_current_limit_amperes: float
    valid_hall_codes: tuple[int, ...]
    positive_phase_table: dict[int, tuple[int, int, int]]
    negative_phase_table: dict[int, tuple[int, int, int]]
    controller_contract_bound: float


def compile_contract(model: Path = MODEL) -> MotorSafetyContract:
    """Extract and validate the exact safety slice used by both proof stages."""
    model = model.resolve()
    source = model.read_text()
    drive = _body(source, "part def HallCommutatedDrive", "part def SpeedController")
    controller = _body(
        source, "part def SpeedController",
        "part def HallSensoredBrushlessMotorSystem")
    system = _body(source, "part def HallSensoredBrushlessMotorSystem", "part system")

    maximum_duty = _one_number(
        source,
        r"attribute\s+:>>\s+maximumDutyMagnitude\s*=\s*([-+0-9.eE]+)\s*;",
        "maximumDutyMagnitude value",
    )
    current_limit = _one_number(
        source,
        r"attribute\s+:>>\s+configuredCurrentLimitAmperes\s*=\s*([-+0-9.eE]+)\s*;",
        "configuredCurrentLimitAmperes value",
    )
    if maximum_duty <= 0.0 or current_limit <= 0.0:
        raise ValueError("duty and current limits must both be positive")

    # Saturation must be an exhaustive, non-overlapping three-way partition.
    _require_regex(
        drive,
        r"if\s+proposal\.fraction\s*>\s*maximumDutyMagnitude[^}]*?"
        r"boundedProposedSignedDutyFraction\s*:=\s*maximumDutyMagnitude",
        "upper duty saturation branch",
    )
    _require_regex(
        drive,
        r"if\s+proposal\.fraction\s*<\s*0\.0\s*-\s*maximumDutyMagnitude[^}]*?"
        r"boundedProposedSignedDutyFraction\s*:=\s*0\.0\s*-\s*maximumDutyMagnitude",
        "lower duty saturation branch",
    )
    _require_regex(
        drive,
        r"if\s+proposal\.fraction\s*<=\s*maximumDutyMagnitude\s+and\s+"
        r"proposal\.fraction\s*>=\s*0\.0\s*-\s*maximumDutyMagnitude[^}]*?"
        r"boundedProposedSignedDutyFraction\s*:=\s*proposal\.fraction",
        "in-range duty branch",
    )

    # Invalid-Hall shutdown and the valid-Hall execution relation are part of
    # the certificate boundary; weakening either invalidates compilation.
    _require_regex(
        drive,
        r"if\s+sampledHallCode\s*<\s*1\s+or\s+sampledHallCode\s*>\s*6\s*\{[^}]*?"
        r"executedSignedDutyFraction\s*:=\s*0\.0\s*;[^}]*?"
        r"highSidePwmPhase\s*:=\s*0\s*;[^}]*?"
        r"lowSideOnPhase\s*:=\s*0\s*;[^}]*?"
        r"disconnectedPhase\s*:=\s*0\s*;",
        "invalid-Hall shutdown branch",
    )
    _require_regex(
        drive,
        r"if\s+sampledHallCode\s*>=\s*1\s+and\s+sampledHallCode\s*<=\s*6\s*\{[^}]*?"
        r"executedSignedDutyFraction\s*:=\s*boundedProposedSignedDutyFraction",
        "valid-Hall execution branch",
    )

    # Current limiting is deliberately certified only as a directional
    # surrogate.  This is not a physical-current <= 6 A theorem.
    limiter_patterns = (
        r"sampledPairCurrentAmperes\s*>=\s*configuredCurrentLimitAmperes\s+and\s+"
        r"policyCall\.proposedSignedDutyFraction\s*>\s*0\.0\s*\{\s*"
        r"assign\s+lastCurrentLimitedSignedDutyFraction\s*:=\s*0\.0",
        r"sampledPairCurrentAmperes\s*<=\s*0\.0\s*-\s*configuredCurrentLimitAmperes\s+and\s+"
        r"policyCall\.proposedSignedDutyFraction\s*<\s*0\.0\s*\{\s*"
        r"assign\s+lastCurrentLimitedSignedDutyFraction\s*:=\s*0\.0",
        r"lastCurrentLimitedSignedDutyFraction\s*:=\s*"
        r"policyCall\.proposedSignedDutyFraction",
    )
    for index, pattern in enumerate(limiter_patterns, 1):
        _require_regex(controller, pattern, f"current-limiter branch {index}")

    controller_bound = _one_number(
        controller,
        r"p\.proposedSignedDutyFraction\s*>=\s*-([-+0-9.eE]+)",
        "neural proposal lower bound",
    )
    upper_bound = _one_number(
        controller,
        r"p\.proposedSignedDutyFraction\s*<=\s*([-+0-9.eE]+)",
        "neural proposal upper bound",
    )
    if controller_bound != upper_bound or controller_bound != maximum_duty:
        raise ValueError("controller contract and drive duty bounds disagree")

    def validate_table(
        table: dict[int, tuple[int, int, int]], relation: str,
    ) -> None:
        for hall, (high, low, disconnected) in table.items():
            pattern = (
                rf"executedSignedDutyFraction\s*{relation}\s*0\.0\s+and\s+"
                rf"sampledHallCode\s*==\s*{hall}\s*\{{[^}}]*?"
                rf"highSidePwmPhase\s*:=\s*{high}\s*;[^}}]*?"
                rf"lowSideOnPhase\s*:=\s*{low}\s*;[^}}]*?"
                rf"disconnectedPhase\s*:=\s*{disconnected}\s*;"
            )
            _require_regex(drive, pattern, f"Hall {hall} phase tuple")

    validate_table(POSITIVE_TABLE, r">=")
    validate_table(NEGATIVE_TABLE, r"<")

    for requirement in (
        "Executed Duty Within Authorized Range",
        "Invalid Hall State Disables Drive",
        "Current Limit Surrogate Opposes Further Increase",
        "Controller Supplies Bounded Duty Proposal",
        "Valid Hall Commutation Uses Distinct Phases",
    ):
        if f"requirement def '{requirement}'" not in system:
            raise ValueError(f"required safety requirement is missing: {requirement}")

    return MotorSafetyContract(
        model=str(model),
        model_sha256=_sha256(model),
        maximum_duty_magnitude=maximum_duty,
        configured_current_limit_amperes=current_limit,
        valid_hall_codes=tuple(range(1, 7)),
        positive_phase_table=dict(POSITIVE_TABLE),
        negative_phase_table=dict(NEGATIVE_TABLE),
        controller_contract_bound=controller_bound,
    )


def certify_structure(contract: MotorSafetyContract) -> dict:
    """Issue an exact finite/algebraic certificate for the recognized slice."""
    limit = contract.maximum_duty_magnitude
    checks: list[dict] = []

    # The three source branches are a partition of the real proposal line.
    saturation_regions = (
        ("below", -limit),
        ("inside", "identity-on-closed-interval"),
        ("above", limit),
    )
    for region, output in saturation_regions:
        checks.append({
            "kind": "duty-saturation-region",
            "region": region,
            "output": output,
            "proved": True,
        })

    # For high measured current, positive proposals map to zero and all other
    # proposals are non-positive.  The low-current proof is symmetric.
    for current_region, proposal_sign, output_sign in (
        ("at-or-above-positive-limit", "positive", "zero"),
        ("at-or-above-positive-limit", "non-positive", "non-positive"),
        ("at-or-below-negative-limit", "negative", "zero"),
        ("at-or-below-negative-limit", "non-negative", "non-negative"),
    ):
        checks.append({
            "kind": "current-limiter-sign-region",
            "current_region": current_region,
            "proposal_sign": proposal_sign,
            "output_sign": output_sign,
            "proved": True,
        })

    # Hall 000 and 111 are the only invalid values in the declared 3-bit
    # domain.  Every valid code has an exact source-checked phase tuple in
    # each direction, and every tuple is a permutation of phases 1,2,3.
    for hall in range(8):
        if hall not in contract.valid_hall_codes:
            checks.append({
                "kind": "invalid-hall-shutdown", "hall_code": hall,
                "executed_duty": 0.0, "phases": [0, 0, 0], "proved": True,
            })
            continue
        for direction, table in (
            ("non-negative", contract.positive_phase_table),
            ("negative", contract.negative_phase_table),
        ):
            phases = table[hall]
            checks.append({
                "kind": "valid-hall-commutation",
                "hall_code": hall,
                "direction": direction,
                "phases": list(phases),
                "proved": sorted(phases) == [1, 2, 3],
            })

    proved = all(check["proved"] for check in checks)
    return {
        "proved": proved,
        "method": "fail-closed-source-shape-and-exhaustive-branch-partition",
        "model": contract.model,
        "model_sha256": contract.model_sha256,
        "scope": [
            "normalized executed-duty bound",
            "invalid-Hall shutdown",
            "directional measured-current limiter",
            "valid-Hall phase-role well-formedness",
            "pinned Hall commutation table",
        ],
        "explicit_non_claims": [
            "physical current remains within 6 A",
            "switching-level electrical safety",
            "thermal safety",
            "plant trajectory safety",
        ],
        "checks": checks,
    }


def _smv_case_table(
    table: dict[int, tuple[int, int, int]], tuple_index: int, relation: str,
) -> list[str]:
    return [
        f"    executed_duty {relation} 0.0 & hall_code = {hall} : {phases[tuple_index]};"
        for hall, phases in table.items()
    ]


def emit_smv(contract: MotorSafetyContract, destination: Path) -> Path:
    """Emit the compact semantic cross-check consumed by nuXmv."""
    duty = format(contract.maximum_duty_magnitude, ".17g")
    current = format(contract.configured_current_limit_amperes, ".17g")

    def phase_define(name: str, index: int) -> str:
        rows = [f"  {name} := case", "    !valid_hall : 0;"]
        rows.extend(_smv_case_table(
            contract.positive_phase_table, index, ">="))
        rows.extend(_smv_case_table(
            contract.negative_phase_table, index, "<"))
        rows.extend(["    TRUE : 0;", "  esac;"])
        return "\n".join(rows)

    table_terms = []
    for relation, table in ((">=", contract.positive_phase_table),
                            ("<", contract.negative_phase_table)):
        for hall, phases in table.items():
            high, low, disconnected = phases
            table_terms.append(
                f"((executed_duty {relation} 0.0 & hall_code = {hall}) -> "
                f"(high_phase = {high} & low_phase = {low} & "
                f"disconnected_phase = {disconnected}))")
    exact_table = " & ".join(table_terms)

    source = f"""-- Compact safety slice compiled from: {contract.model}
-- Source SHA-256: {contract.model_sha256}
-- This model intentionally excludes plant and sensor trajectory dynamics.
MODULE main
VAR
  policy_proposal : real;
  measured_pair_current : real;
  hall_code : 0..7;

-- The neural requirement is an explicit assume-guarantee contract, not a
-- proof about arbitrary learned weights.
INVAR policy_proposal >= -{duty} & policy_proposal <= {duty}

DEFINE
  current_limited_duty := case
    measured_pair_current >= {current} & policy_proposal > 0.0 : 0.0;
    measured_pair_current <= -{current} & policy_proposal < 0.0 : 0.0;
    TRUE : policy_proposal;
  esac;
  bounded_duty := case
    current_limited_duty > {duty} : {duty};
    current_limited_duty < -{duty} : -{duty};
    TRUE : current_limited_duty;
  esac;
  valid_hall := hall_code >= 1 & hall_code <= 6;
  executed_duty := case
    !valid_hall : 0.0;
    TRUE : bounded_duty;
  esac;
{phase_define("high_phase", 0)}
{phase_define("low_phase", 1)}
{phase_define("disconnected_phase", 2)}

-- Requirement: Executed Duty Within Authorized Range
INVARSPEC executed_duty >= -{duty} & executed_duty <= {duty}

-- Requirement: Invalid Hall State Disables Drive
INVARSPEC !valid_hall -> (executed_duty = 0.0 & high_phase = 0 & low_phase = 0 & disconnected_phase = 0)

-- Requirement: Current Limit Surrogate Opposes Further Increase
INVARSPEC (measured_pair_current >= {current} -> current_limited_duty <= 0.0) & (measured_pair_current <= -{current} -> current_limited_duty >= 0.0)

-- Requirement: Controller Supplies Bounded Duty Proposal
INVARSPEC policy_proposal >= -{duty} & policy_proposal <= {duty}

-- Requirement: Valid Hall Commutation Uses Distinct Phases
INVARSPEC valid_hall -> (high_phase >= 1 & high_phase <= 3 & low_phase >= 1 & low_phase <= 3 & disconnected_phase >= 1 & disconnected_phase <= 3 & high_phase != low_phase & high_phase != disconnected_phase & low_phase != disconnected_phase)

-- Auxiliary invariant: exact source commutation table
INVARSPEC {exact_table}
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source)
    return destination


def run(
    model: Path,
    output: Path,
    *,
    nuxmv: Path | None,
    timeout_seconds: int,
) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    contract = compile_contract(model)
    contract_json = asdict(contract)
    contract_json["positive_phase_table"] = {
        str(key): list(value)
        for key, value in contract.positive_phase_table.items()
    }
    contract_json["negative_phase_table"] = {
        str(key): list(value)
        for key, value in contract.negative_phase_table.items()
    }
    (output / "contract.json").write_text(
        json.dumps(contract_json, indent=2, sort_keys=True) + "\n")

    structural = certify_structure(contract)
    (output / "structural-certificate.json").write_text(
        json.dumps(structural, indent=2, sort_keys=True) + "\n")

    smv = emit_smv(contract, output / "motor-safety.smv")
    semantic = None
    if nuxmv is not None:
        semantic = verify_smv(
            smv, output / "nuxmv", nuxmv=nuxmv,
            timeout_seconds=timeout_seconds,
            model=model,
        )

    report = {
        "model": str(model.resolve()),
        "model_sha256": contract.model_sha256,
        "structural": structural,
        "smv": str(smv.resolve()),
        "smv_sha256": _sha256(smv),
        "nuxmv": semantic,
        "structural_verified": structural["proved"],
        "nuxmv_verified": None if semantic is None else semantic["verified"],
        "verified": bool(
            structural["proved"] and semantic is not None
            and semantic["verified"]),
    }
    (output / "verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--nuxmv", type=Path)
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")
    if args.output.exists():
        parser.error(f"output directory already exists: {args.output}")
    if args.nuxmv is not None and not args.nuxmv.is_file():
        parser.error(f"nuXmv executable not found: {args.nuxmv}")

    report = run(
        args.model, args.output.resolve(), nuxmv=args.nuxmv,
        timeout_seconds=args.timeout)
    if args.nuxmv is None:
        print("Structural certificate proved; nuXmv stage generated but not run")
        return 0
    print("Motor safety verification proved" if report["verified"]
          else "Motor safety verification failed")
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
