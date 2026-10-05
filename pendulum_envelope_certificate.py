"""Compile and certify the corrected pendulum's continuous safety envelope."""

from __future__ import annotations

import json
from pathlib import Path
import sys

from affine_safety_certificate import (
    ScalarSafetyObjective,
    certify_scalar_affine_safety,
)
from symbolic_transition import (
    UnsaturatedActuator,
    compile_unsaturated_scan_cycle,
    constant_definition,
)


SAFETY_STATE = "plant_pendulumAngleFromUprightRadians"
MODE_STATE = "amplifier_executedVoltage"
PARAMETER = "controller_targetArmAngleRadians"
PREFIX_STEPS = 2600
BLOCK_STEPS = 2000


def certify(smv: Path) -> dict[str, object]:
    source = smv.read_text()
    transition = compile_unsaturated_scan_cycle(
        source,
        actuator=UnsaturatedActuator(
            executed_state=MODE_STATE,
            proposal_symbol="amplifier_proposal_volts",
            availability_symbol=(
                "amplifier_proposalPort_MotorVoltageCommand_available"),
            limit_symbol="amplifier_maximumVoltageMagnitude",
        ),
    ).dependency_slice((SAFETY_STATE, MODE_STATE))
    report = certify_scalar_affine_safety(
        transition,
        ScalarSafetyObjective(
            parameter=PARAMETER,
            safety_state=SAFETY_STATE,
            safety_bound=constant_definition(
                source, "controller_captureAngleRadians"),
            mode_state=MODE_STATE,
            mode_bound=constant_definition(
                source, "amplifier_maximumVoltageMagnitude"),
            prefix_steps=PREFIX_STEPS,
            block_steps=BLOCK_STEPS,
        ),
    )
    report.update({
        "proof": "finite-prefix-plus-block-contraction",
        "safety_state": SAFETY_STATE,
        "mode_state": MODE_STATE,
        "compiled_physical_cycle": transition.metadata["compiled_phases"],
    })
    return report


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {Path(sys.argv[0]).name} MODEL.smv", file=sys.stderr)
        return 2
    print(json.dumps(certify(Path(sys.argv[1])), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
