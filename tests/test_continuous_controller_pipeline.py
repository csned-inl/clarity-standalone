"""Focused regressions for the type-driven continuous controller path."""

import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tmp_validation"))
sys.path.insert(0, str(ROOT / "rl"))

from continuous_spec import ExactContinuousShield, UnsupportedContinuousContract


MODEL = ROOT / "sysml-models/rotary-inverted-pendulum/model.sysml"
EXTRACTOR = ROOT / "sysml-models/mc-extract.py"


class ContinuousControllerPipelineTests(unittest.TestCase):
    def test_exact_real_interface_is_extracted_without_model_dispatch(self):
        shield = ExactContinuousShield(str(MODEL))
        self.assertEqual(shield.interface.output_name, "proposedMotorVoltage")
        self.assertEqual(shield.interface.output_type, "Real")
        self.assertEqual(
            shield.interface.input_names,
            (
                "armAngleRadians",
                "pendulumAngleFromUprightRadians",
                "estimatedArmAngularVelocityRadiansPerSecond",
                "estimatedPendulumAngularVelocityRadiansPerSecond",
                "targetArmAngleRadians",
                "done",
            ),
        )
        self.assertNotIn("done", shield.interface.required_input_names)
        source = (ROOT / "rl/continuous_spec.py").read_text()
        self.assertNotIn("rotary-inverted-pendulum", source)
        self.assertNotIn("proposedMotorVoltage", source)

    def test_required_action_is_the_source_feedback_equation(self):
        shield = ExactContinuousShield(str(MODEL))
        observation = {
            "armAngleRadians": 0.1,
            "pendulumAngleFromUprightRadians": 0.02,
            "estimatedArmAngularVelocityRadiansPerSecond": 0.3,
            "estimatedPendulumAngularVelocityRadiansPerSecond": -0.4,
            "targetArmAngleRadians": 0.5,
            "done": False,
        }
        expected = 0.0 - (
            -3.8730 * (0.1 - 0.5)
            + 51.2299 * 0.02
            + -2.2650 * 0.3
            + 4.3458 * -0.4
        )
        self.assertEqual(shield.required_action(observation), expected)
        executed, overridden, correction = shield.select(0.0, observation)
        self.assertEqual(executed, expected)
        self.assertTrue(overridden)
        self.assertEqual(correction, abs(expected))

    def test_nonfinite_inputs_fail_closed(self):
        shield = ExactContinuousShield(str(MODEL))
        observation = {name: 0.0 for name in shield.interface.input_names}
        observation["done"] = False
        observation["armAngleRadians"] = math.nan
        with self.assertRaisesRegex(ValueError, "non-finite"):
            shield.required_action(observation)

    def test_smv_extractor_preserves_real_neural_output_type(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            smv = Path(directory) / "model.smv"
            subprocess.run(
                [sys.executable, str(EXTRACTOR), str(MODEL),
                 "--dt", "0.001", "-o", str(smv)],
                cwd=ROOT, check=True, capture_output=True, text=True)
            source = smv.read_text()
        self.assertIn(
            "controller_policyCall_proposedMotorVoltage : real;", source)
        self.assertNotIn(
            "controller_policyCall_proposedMotorVoltage : boolean;", source)
        self.assertEqual(source.count("INVARSPEC"), 3)


if __name__ == "__main__":
    unittest.main()
