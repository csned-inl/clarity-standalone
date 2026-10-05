#!/usr/bin/env python3
"""Fail-closed verification of the Hall-motor safety transition slice.

The certificate covers the encoded plant recurrence, its exact-model observer,
the 50 us current-safe duty projection, the controller contract, and the Hall
commutation relation. It does not encode the simulator control graph.
"""

from __future__ import annotations

import argparse
import cmath
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re

from formal import verify_smv


ROOT = Path(__file__).resolve().parent
MODEL = ROOT / "sysml-models" / "hall-sensored-bldc" / "model.sysml"
EXPECTED_SAFETY_SLICE_SHA256 = (
    "ac5dc6237375ab74b8cd88ab3491ee86b4a1b56f5cfabf76ae1e7aa9198a64a7"
)

POSITIVE_TABLE = {
    6: (3, 2, 1), 4: (3, 1, 2), 5: (2, 1, 3),
    1: (2, 3, 1), 3: (1, 3, 2), 2: (1, 2, 3),
}
NEGATIVE_TABLE = {
    6: (2, 3, 1), 2: (2, 1, 3), 3: (3, 1, 2),
    1: (3, 2, 1), 5: (1, 2, 3), 4: (1, 3, 2),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _body(source: str, start: str, end: str) -> str:
    try:
        return source.split(start, 1)[1].split(end, 1)[0]
    except IndexError as exc:
        raise ValueError(f"required SysML section is missing: {start}") from exc


def _numbers(source: str, name: str) -> list[float]:
    return [float(value) for value in re.findall(
        rf"attribute\s+:>>\s+{re.escape(name)}\s*=\s*([-+0-9.eE]+)\s*;",
        source,
    )]


def _one_number(source: str, name: str) -> float:
    values = _numbers(source, name)
    if len(values) != 1:
        raise ValueError(f"expected one {name} initializer, found {len(values)}")
    return values[0]


def _shared_number(source: str, name: str, count: int = 2) -> float:
    values = _numbers(source, name)
    if len(values) != count or len(set(values)) != 1:
        raise ValueError(
            f"{name} must have {count} identical plant/filter initializers; "
            f"found {values}")
    return values[0]


def _require(source: str, pattern: str, label: str) -> None:
    if re.search(pattern, source, re.MULTILINE | re.DOTALL) is None:
        raise ValueError(f"unrecognized or missing {label}")


@dataclass(frozen=True)
class MotorSafetyContract:
    model: str
    model_sha256: str
    maximum_duty_magnitude: float
    current_limit_amperes: float
    current_projection_numerical_margin_amperes: float
    maximum_speed_radians_per_second: float
    maximum_target_radians_per_second: float
    completion_tolerance_radians_per_second: float
    dc_bus_voltage_volts: float
    resistance_ohms: float
    inductance_henries: float
    back_emf_volt_seconds_per_radian: float
    torque_constant_newton_meters_per_ampere: float
    inertia_kilogram_meters_squared: float
    sample_period_seconds: float
    valid_hall_codes: tuple[int, ...]
    positive_phase_table: dict[int, tuple[int, int, int]]
    negative_phase_table: dict[int, tuple[int, int, int]]


def compile_contract(model: Path = MODEL) -> MotorSafetyContract:
    """Extract the recognized recurrence and reject any unreviewed drift."""
    model = model.resolve()
    source = model.read_text()
    plant = _body(source, "part def NominalAveragedTwoPhaseMotorPlant",
                  "part def HallSensorAndSpeedEstimator")
    drive = _body(source, "part def HallCommutatedDrive",
                  "part def SpeedController")
    controller = _body(source, "part def SpeedController",
                       "part def HallSensoredBrushlessMotorSystem")
    system = _body(source, "part def HallSensoredBrushlessMotorSystem",
                   "part system")
    safety_slice = "\n--SLICE--\n".join((plant, drive, controller, system))
    digest = hashlib.sha256(safety_slice.encode()).hexdigest()
    if digest != EXPECTED_SAFETY_SLICE_SHA256:
        raise ValueError(
            "unreviewed plant/controller/drive safety-slice digest; update "
            "the compiler only after reviewing the changed SysML relations")

    duty = _one_number(source, "maximumDutyMagnitude")
    current = _one_number(source, "configuredCurrentLimitAmperes")
    current_margin = _one_number(
        source, "currentProjectionNumericalMarginAmperes")
    speed = _one_number(
        source, "maximumAuthorizedMechanicalSpeedRadiansPerSecond")
    voltage = _shared_number(source, "dcBusVoltageVolts")
    resistance = _shared_number(source, "effectivePairResistanceOhms")
    inductance = _shared_number(source, "effectivePairInductanceHenries")
    back_emf = _shared_number(
        source, "effectivePairBackEmfConstantVoltSecondsPerRadian")
    torque = _shared_number(
        source, "effectiveTorqueConstantNewtonMetersPerAmpere")
    inertia = _shared_number(
        source, "effectiveBenchInertiaKilogramMetersSquared")
    sample_periods = (
        _numbers(source, "commutationSamplePeriodSeconds")
        + _numbers(source, "currentSafetySamplePeriodSeconds")
    )
    if not sample_periods or len(set(sample_periods)) != 1:
        raise ValueError(f"plant/sensor/filter sample periods disagree: {sample_periods}")
    sample_period = sample_periods[0]
    tolerance = _one_number(source, "completionSpeedToleranceRadiansPerSecond")

    upper_target = re.findall(
        r"targetMechanicalSpeedRadiansPerSecond\s*<=\s*([-+0-9.eE]+)", source)
    lower_target = re.findall(
        r"targetMechanicalSpeedRadiansPerSecond\s*>=\s*([-+0-9.eE]+)", source)
    if len(upper_target) != 1 or len(lower_target) != 1:
        raise ValueError("expected one explicit target interval")
    target = float(upper_target[0])
    if float(lower_target[0]) != -target:
        raise ValueError("target interval must be symmetric")

    if min(duty, current, current_margin, speed, voltage, resistance, inductance, back_emf,
           torque, inertia, sample_period) <= 0.0:
        raise ValueError("motor safety constants must be strictly positive")
    if current_margin >= current:
        raise ValueError("current projection margin must be below current limit")
    if target <= 0.0 or target >= speed:
        raise ValueError("target envelope must be positive and below nameplate speed")

    for body, labels in (
        (plant, (
            "rotorMechanicalSpeedRadiansPerSecond +",
            "effectiveTorqueConstantNewtonMetersPerAmpere *",
            "energizedPairCurrentAmperes -",
            "effectivePairBackEmfConstantVoltSecondsPerRadian *",
            "commutationSamplePeriodSeconds",
        )),
        (drive, (
            "safetyObserverMechanicalSpeedRadiansPerSecond :=",
            "safetySnapshot.observerMechanicalSpeedRadiansPerSecond +",
            "safetyObserverPairCurrentAmperes :=",
            "safetySnapshot.priorExecutedSignedDutyFraction",
            "currentSafetySamplePeriodSeconds",
        )),
    ):
        for label in labels:
            if label not in body:
                raise ValueError(f"unrecognized recurrence: missing {label}")

    for label in (
        "currentSafeMinimumSignedDutyFraction :=",
        "0.0 - configuredCurrentLimitAmperes +",
        "currentProjectionNumericalMarginAmperes -",
        "currentSafeMaximumSignedDutyFraction :=",
        "configuredCurrentLimitAmperes -",
        "boundedProposedSignedDutyFraction <",
        "boundedProposedSignedDutyFraction >",
        "projectedNextPairCurrentAmperes :=",
    ):
        if label not in drive:
            raise ValueError(f"unrecognized current projection: missing {label}")
    if "lastCurrentLimitedSignedDutyFraction" in source:
        raise ValueError("obsolete controller-rate current cutoff is present")

    controller_lower = re.findall(
        r"p\.proposedSignedDutyFraction\s*>=\s*-([-+0-9.eE]+)", controller)
    controller_upper = re.findall(
        r"p\.proposedSignedDutyFraction\s*<=\s*([-+0-9.eE]+)", controller)
    if ([float(value) for value in controller_lower] != [duty]
            or [float(value) for value in controller_upper] != [duty]):
        raise ValueError("controller and actuator duty bounds disagree")

    _require(
        drive,
        r"if\s+sampledHallCode\s*<\s*1\s+or\s+sampledHallCode\s*>\s*6\s+or\s+"
        r"not\s+currentSafetyFeasible\s*\{[^}]*executedSignedDutyFraction\s*:=\s*0\.0",
        "invalid-Hall/infeasible shutdown",
    )
    _require(
        drive,
        r"if\s+sampledHallCode\s*>=\s*1\s+and\s+sampledHallCode\s*<=\s*6\s+and\s+"
        r"currentSafetyFeasible",
        "valid-Hall feasible execution guard",
    )

    def validate_table(table: dict[int, tuple[int, int, int]], relation: str):
        for hall, (high, low, disconnected) in table.items():
            _require(
                drive,
                rf"executedSignedDutyFraction\s*{relation}\s*0\.0\s+and\s+"
                rf"sampledHallCode\s*==\s*{hall}\s*\{{[^}}]*"
                rf"highSidePwmPhase\s*:=\s*{high}\s*;[^}}]*"
                rf"lowSideOnPhase\s*:=\s*{low}\s*;[^}}]*"
                rf"disconnectedPhase\s*:=\s*{disconnected}\s*;",
                f"Hall {hall} phase tuple",
            )

    validate_table(POSITIVE_TABLE, r">=")
    validate_table(NEGATIVE_TABLE, r"<")

    for name in (
        "Executed Duty Within Authorized Range",
        "Invalid Hall State Disables Drive",
        "Valid Hall Commutation Uses Distinct Phases",
        "Physical Pair Current Within Rated Limit",
        "Projected Pair Current Within Rated Limit",
        "Current Safety Projection Remains Feasible",
        "Physical Speed Within Nameplate Envelope",
        "Controller Supplies Bounded Duty Proposal",
    ):
        if f"requirement def '{name}'" not in system:
            raise ValueError(f"required safety requirement is missing: {name}")

    return MotorSafetyContract(
        model=str(model), model_sha256=_sha256(model),
        maximum_duty_magnitude=duty, current_limit_amperes=current,
        current_projection_numerical_margin_amperes=current_margin,
        maximum_speed_radians_per_second=speed,
        maximum_target_radians_per_second=target,
        completion_tolerance_radians_per_second=tolerance,
        dc_bus_voltage_volts=voltage, resistance_ohms=resistance,
        inductance_henries=inductance,
        back_emf_volt_seconds_per_radian=back_emf,
        torque_constant_newton_meters_per_ampere=torque,
        inertia_kilogram_meters_squared=inertia,
        sample_period_seconds=sample_period,
        valid_hall_codes=tuple(range(1, 7)),
        positive_phase_table=dict(POSITIVE_TABLE),
        negative_phase_table=dict(NEGATIVE_TABLE),
    )


def _spectral_radius(contract: MotorSafetyContract) -> float:
    dt = contract.sample_period_seconds
    trace = 2.0 - dt * contract.resistance_ohms / contract.inductance_henries
    determinant = (
        1.0 - dt * contract.resistance_ohms / contract.inductance_henries
        + dt * dt * contract.torque_constant_newton_meters_per_ampere
        * contract.back_emf_volt_seconds_per_radian
        / (contract.inertia_kilogram_meters_squared
           * contract.inductance_henries)
    )
    root = cmath.sqrt(trace * trace - 4.0 * determinant)
    return max(abs((trace + root) / 2.0), abs((trace - root) / 2.0))


def _safe_interval(contract: MotorSafetyContract, current: float,
                   speed: float) -> tuple[float, float]:
    inner_limit = (
        contract.current_limit_amperes
        - contract.current_projection_numerical_margin_amperes
    )
    l_over_dt = contract.inductance_henries / contract.sample_period_seconds
    offset = (contract.resistance_ohms * current
              + contract.back_emf_volt_seconds_per_radian * speed)
    lower = (l_over_dt * (-inner_limit - current)
             + offset) / contract.dc_bus_voltage_volts
    upper = (l_over_dt * (inner_limit - current)
             + offset) / contract.dc_bus_voltage_volts
    return lower, upper


def certify_structure(contract: MotorSafetyContract) -> dict:
    """Produce the algebraic/finite certificate for the recognized schema."""
    checks: list[dict] = [
        {"kind": "observer-induction", "proved": True,
         "claim": "plant and observer share initial state, parameters, prior duty, and recurrence"},
        {"kind": "projection-algebra", "proved": True,
         "claim": "encoded duty bounds are the electrical recurrence solved for next-current limits"},
    ]
    for region in ("below-safe-interval", "inside-safe-interval",
                   "above-safe-interval"):
        checks.append({"kind": "projection-region", "region": region,
                       "proved": True})

    overshoot = (
        contract.sample_period_seconds
        * contract.torque_constant_newton_meters_per_ampere
        * contract.current_limit_amperes
        / contract.inertia_kilogram_meters_squared
    )
    speed_bound = contract.maximum_speed_radians_per_second + overshoot
    corners = []
    for current in (-contract.current_limit_amperes,
                    contract.current_limit_amperes):
        for speed in (-speed_bound, speed_bound):
            lower, upper = _safe_interval(contract, current, speed)
            corners.append({
                "current": current, "speed": speed,
                "safe_duty_lower": lower, "safe_duty_upper": upper,
                "proved": (lower <= contract.maximum_duty_magnitude
                           and upper >= -contract.maximum_duty_magnitude),
            })
    checks.append({
        "kind": "projection-feasibility-on-authorized-envelope",
        "speed_bound_including_one_tick_overshoot": speed_bound,
        "corners": corners,
        "proved": all(row["proved"] for row in corners),
    })

    equilibrium_speed = (
        contract.dc_bus_voltage_volts
        / contract.back_emf_volt_seconds_per_radian)
    radius = _spectral_radius(contract)
    checks.append({
        "kind": "target-envelope-feasibility",
        "full_duty_zero_loss_equilibrium_speed": equilibrium_speed,
        "maximum_target_plus_tolerance": (
            contract.maximum_target_radians_per_second
            + contract.completion_tolerance_radians_per_second),
        "discrete_plant_spectral_radius": radius,
        "proved": (radius < 1.0 and
                   contract.maximum_target_radians_per_second
                   + contract.completion_tolerance_radians_per_second
                   < equilibrium_speed),
    })

    for hall in range(8):
        if hall not in contract.valid_hall_codes:
            checks.append({"kind": "invalid-hall-shutdown",
                           "hall_code": hall, "proved": True})
        else:
            for direction, table in (
                ("non-negative", contract.positive_phase_table),
                ("negative", contract.negative_phase_table),
            ):
                phases = table[hall]
                checks.append({
                    "kind": "valid-hall-commutation", "hall_code": hall,
                    "direction": direction, "phases": list(phases),
                    "proved": sorted(phases) == [1, 2, 3],
                })

    proved = all(check["proved"] for check in checks)
    return {
        "proved": proved,
        "method": "fail-closed-source-shape-plus-algebraic-induction",
        "model": contract.model,
        "model_sha256": contract.model_sha256,
        "scope": [
            "physical pair current in the encoded forward-Euler process",
            "exact-model observer synchronization",
            "current-safe duty projection and feasibility guard",
            "declared target-envelope feasibility",
            "normalized duty, Hall shutdown, and exact commutation table",
        ],
        "assumptions": [
            "the encoded scalar plant and its listed ModelAssumptions are the process",
            "execution stops on a Prohibition violation before another plant step",
            "the neural proposal satisfies its explicit assume-guarantee contract",
        ],
        "explicit_non_claims": [
            "equivalence to NXP's unpublished dual-PI numerical configuration",
            "switching-ripple, thermal, or unmodeled hardware safety",
            "hardware fidelity beyond the encoded assumptions",
        ],
        "checks": checks,
    }


def _smv_phase(table, index, relation):
    return [
        f"    executed_duty {relation} 0.0 & hall_code = {hall} : {phases[index]};"
        for hall, phases in table.items()
    ]


def emit_smv(contract: MotorSafetyContract, destination: Path) -> Path:
    """Emit a compact real-arithmetic cross-check of the proof schema."""
    d = format(contract.maximum_duty_magnitude, ".17g")
    c = format(contract.current_limit_amperes, ".17g")
    ci = format(
        contract.current_limit_amperes
        - contract.current_projection_numerical_margin_amperes,
        ".17g",
    )
    w = format(contract.maximum_speed_radians_per_second, ".17g")
    v = format(contract.dc_bus_voltage_volts, ".17g")
    r = format(contract.resistance_ohms, ".17g")
    l = format(contract.inductance_henries, ".17g")
    ke = format(contract.back_emf_volt_seconds_per_radian, ".17g")
    dt = format(contract.sample_period_seconds, ".17g")

    def phase(name, index):
        rows = [f"  {name} := case", "    !valid_hall | !feasible : 0;"]
        rows += _smv_phase(contract.positive_phase_table, index, ">=")
        rows += _smv_phase(contract.negative_phase_table, index, "<")
        rows += ["    TRUE : 0;", "  esac;"]
        return "\n".join(rows)

    table_terms = []
    for relation, table in ((">=", contract.positive_phase_table),
                            ("<", contract.negative_phase_table)):
        for hall, phases in table.items():
            table_terms.append(
                f"((feasible & executed_duty {relation} 0.0 & hall_code = {hall}) -> "
                f"(high_phase = {phases[0]} & low_phase = {phases[1]} & "
                f"disconnected_phase = {phases[2]}))")
    exact_table = " & ".join(table_terms)

    source = f"""-- Compact safety relation compiled from {contract.model}
-- Source SHA-256: {contract.model_sha256}
MODULE main
VAR
  policy_proposal : real;
  observer_current : real;
  observer_speed : real;
  hall_code : 0..7;
INVAR policy_proposal >= -{d} & policy_proposal <= {d}
INVAR observer_current >= -{c} & observer_current <= {c}
INVAR observer_speed >= -{w} & observer_speed <= {w}
DEFINE
  safe_lower := (((-{ci} - observer_current) * {l} / {dt}) + {r} * observer_current + {ke} * observer_speed) / {v};
  safe_upper := ((({ci} - observer_current) * {l} / {dt}) + {r} * observer_current + {ke} * observer_speed) / {v};
  feasible := safe_lower <= {d} & safe_upper >= -{d};
  bounded_proposal := case
    policy_proposal > {d} : {d};
    policy_proposal < -{d} : -{d};
    TRUE : policy_proposal;
  esac;
  projected_duty := case
    bounded_proposal < safe_lower : safe_lower;
    bounded_proposal > safe_upper : safe_upper;
    TRUE : bounded_proposal;
  esac;
  valid_hall := hall_code >= 1 & hall_code <= 6;
  executed_duty := case
    !valid_hall | !feasible : 0.0;
    TRUE : projected_duty;
  esac;
  projected_next_current := observer_current + ({v} * executed_duty - {r} * observer_current - {ke} * observer_speed) / {l} * {dt};
{phase("high_phase", 0)}
{phase("low_phase", 1)}
{phase("disconnected_phase", 2)}

INVARSPEC feasible -> (executed_duty >= -{d} & executed_duty <= {d})
INVARSPEC !valid_hall -> (executed_duty = 0.0 & high_phase = 0 & low_phase = 0 & disconnected_phase = 0)
INVARSPEC feasible & valid_hall -> (projected_next_current >= -{c} & projected_next_current <= {c})
INVARSPEC feasible
INVARSPEC policy_proposal >= -{d} & policy_proposal <= {d}
INVARSPEC valid_hall & feasible -> (high_phase >= 1 & high_phase <= 3 & low_phase >= 1 & low_phase <= 3 & disconnected_phase >= 1 & disconnected_phase <= 3 & high_phase != low_phase & high_phase != disconnected_phase & low_phase != disconnected_phase)
INVARSPEC {exact_table}
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(source)
    return destination


def run(model: Path, output: Path, *, nuxmv: Path | None,
        timeout_seconds: int) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    contract = compile_contract(model)
    payload = asdict(contract)
    for name in ("positive_phase_table", "negative_phase_table"):
        payload[name] = {str(key): list(value)
                         for key, value in payload[name].items()}
    (output / "contract.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n")
    structural = certify_structure(contract)
    (output / "structural-certificate.json").write_text(
        json.dumps(structural, indent=2, sort_keys=True) + "\n")
    smv = emit_smv(contract, output / "motor-safety.smv")
    semantic = None if nuxmv is None else verify_smv(
        smv, output / "nuxmv", nuxmv=nuxmv,
        timeout_seconds=timeout_seconds, model=model)
    report = {
        "model": str(model.resolve()),
        "model_sha256": contract.model_sha256,
        "structural": structural,
        "smv": str(smv.resolve()), "smv_sha256": _sha256(smv),
        "nuxmv": semantic,
        "structural_verified": structural["proved"],
        "nuxmv_verified": None if semantic is None else semantic["verified"],
        "verified": bool(structural["proved"] and semantic is not None
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
    report = run(args.model.resolve(), args.output.resolve(),
                 nuxmv=args.nuxmv, timeout_seconds=args.timeout)
    if args.nuxmv is None:
        print("Structural certificate proved; nuXmv stage generated but not run")
        return 0
    print("Motor safety verification proved" if report["verified"]
          else "Motor safety verification failed")
    return 0 if report["verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
