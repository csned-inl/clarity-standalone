"""Regressions for exact symbolic scan-cycle and matrix compilation."""

from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from symbolic_transition import (  # noqa: E402
    UnsaturatedActuator,
    compile_unsaturated_scan_cycle,
)


MODEL = ROOT / "sysml-models/rotary-inverted-pendulum/model.sysml"
EXTRACTOR = ROOT / "sysml-models/mc-extract.py"
ACTUATOR = UnsaturatedActuator(
    executed_state="amplifier_executedVoltage",
    proposal_symbol="amplifier_proposal_volts",
    availability_symbol="amplifier_proposalPort_MotorVoltageCommand_available",
    limit_symbol="amplifier_maximumVoltageMagnitude",
)


class SymbolicAffineTransitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            smv = Path(directory) / "model.smv"
            subprocess.run(
                [sys.executable, str(EXTRACTOR), str(MODEL),
                 "--dt", "0.001", "-o", str(smv)],
                cwd=ROOT, check=True, capture_output=True, text=True)
            cls.source = smv.read_text()

    def compile(self, source=None):
        return compile_unsaturated_scan_cycle(
            source or self.source, actuator=ACTUATOR).dependency_slice((
                "plant_pendulumAngleFromUprightRadians",
                "amplifier_executedVoltage",
            ))

    def test_compiler_recovers_exact_closed_loop_recurrence(self):
        system = self.compile()
        self.assertEqual(len(system.states), 19)
        self.assertEqual(
            system.parameters, ("controller_targetArmAngleRadians",))
        self.assertEqual(
            system.parameter_bounds["controller_targetArmAngleRadians"],
            (Fraction("-1.570796326795"), Fraction("1.570796326795")),
        )
        self.assertEqual(
            dict(system.next_state["plant_armAngleRadians"].terms),
            {
                "plant_armAngleRadians": Fraction(1),
                "plant_derivative_armAngleRate": Fraction(1, 1000),
            },
        )
        voltage = dict(system.next_state["amplifier_executedVoltage"].terms)
        self.assertEqual(
            voltage["controller_targetArmAngleRadians"],
            Fraction(-3873, 1000),
        )
        self.assertEqual(
            voltage["encoder_reading_pendulumAngleFromUprightRadians"],
            Fraction(-512299, 10000),
        )
        self.assertEqual(
            system.mode_assumptions,
            ("abs(amplifier_proposal_volts) <= 10",),
        )

    def test_nonlinear_policy_fails_closed(self):
        source = self.source.replace(
            "controller_armAngleGain * "
            "(encoder_reading_armAngleRadians - "
            "controller_targetArmAngleRadians)",
            "encoder_reading_armAngleRadians * "
            "encoder_reading_pendulumAngleFromUprightRadians",
            1,
        )
        with self.assertRaisesRegex(ValueError, "nonlinear multiplication"):
            self.compile(source)

    def test_scan_phase_drift_fails_closed(self):
        source = self.source.replace(
            "amplifier_proposalPort_MotorVoltageCommand_available := "
            "(scan_phase = 1);",
            "amplifier_proposalPort_MotorVoltageCommand_available := "
            "(scan_phase = 0);",
            1,
        )
        with self.assertRaisesRegex(ValueError, "phase-one event"):
            self.compile(source)


if __name__ == "__main__":
    unittest.main()
