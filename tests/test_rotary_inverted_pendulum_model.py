"""Source, wiring, and numerical regressions for the pinned 2019 QUBE process."""
import math
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sysml-models"))

from simulator import ExpressionEvaluator, SimulationEngine, resolve_value
from sysml_parser import SysMLParser


MODEL = ROOT / "sysml-models/rotary-inverted-pendulum/model.sysml"


def source_policy(inputs):
    voltage = 0.0 - (
        -3.8730 * (inputs["armAngleRadians"] - inputs["targetArmAngleRadians"])
        + 51.2299 * inputs["pendulumAngleFromUprightRadians"]
        + -2.2650 * inputs["estimatedArmAngularVelocityRadiansPerSecond"]
        + 4.3458 * inputs["estimatedPendulumAngularVelocityRadiansPerSecond"]
    )
    return {"proposedMotorVoltage": voltage}


class RotaryInvertedPendulumModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parser = SysMLParser(str(MODEL))
        cls.parser.parse()

    def engine(self):
        engine = SimulationEngine(self.parser)
        engine.initialize()
        engine.model = source_policy
        return engine

    def test_source_identity_and_message_wiring(self):
        self.assertEqual(self.parser.system_part, "system")
        self.assertEqual(
            self.parser.connects,
            [
                ("encoder.upstreamPort", "controller.sensorPort"),
                ("controller.proposalPort", "amplifier.proposalPort"),
            ],
        )
        transitions = self.parser.instance_state_machines["system::amplifier"].transitions
        self.assertEqual(len(transitions), 3)
        self.assertEqual(
            {transition.name for transition in transitions},
            {"above_motor_limit", "below_motor_limit", "inside_motor_limit"},
        )

        engine = self.engine()
        expected = {
            "system::plant::armAccelerationFromPendulum": -41.6,
            "system::plant::armAccelerationFromArmRate": -4.16,
            "system::plant::armAccelerationFromPendulumRate": 1.37,
            "system::plant::armAccelerationFromVoltage": 13.9,
            "system::plant::pendulumAccelerationFromPendulum": 72.4,
            "system::plant::pendulumAccelerationFromArmRate": -4.11,
            "system::plant::pendulumAccelerationFromPendulumRate": -2.40,
            "system::plant::pendulumAccelerationFromVoltage": 13.7,
            "system::encoder::velocityFilterCutoffRadiansPerSecond": 50.0,
            "system::controller::armAngleGain": -3.8730,
            "system::controller::pendulumAngleGain": 51.2299,
            "system::controller::armAngularVelocityGain": -2.2650,
            "system::controller::pendulumAngularVelocityGain": 4.3458,
            "system::controller::captureAngleRadians": 0.349065850399,
        }
        for key, value in expected.items():
            self.assertEqual(engine.state[key], value, key)
        self.assertEqual(engine.state["system::plant::pendulumAngleFromUprightRadians"], 0.0)
        self.assertEqual(engine.state["system::encoder::sampledPendulumAngleFromUprightRadians"], 0.0)
        self.assertNotEqual(
            "system::plant::pendulumAngleFromUprightRadians",
            "system::encoder::sampledPendulumAngleFromUprightRadians",
        )
        self.assertEqual(resolve_value(engine.state, "system::samplePeriodSeconds"), 0.001)
        self.assertEqual(engine.state["system::amplifier::maximumVoltageMagnitude"], 10.0)

    def test_amplifier_execution_partition(self):
        cases = [
            (-15.0, -10.0),
            (-10.0, -10.0),
            (0.0, 0.0),
            (10.0, 10.0),
            (15.0, 10.0),
        ]
        for proposed, expected in cases:
            with self.subTest(proposed=proposed):
                engine = self.engine()
                engine.model = lambda _inputs, value=proposed: {
                    "proposedMotorVoltage": value
                }
                engine.step(0.001)
                self.assertEqual(
                    engine.state["system::amplifier::executedVoltage"], expected
                )

    def test_published_feedback_sign_is_the_stable_sign(self):
        a = np.array([
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [0.0, -41.6, -4.16, 1.37],
            [0.0, 72.4, -4.11, -2.40],
        ])
        b = np.array([[0.0], [0.0], [13.9], [13.7]])
        k = np.array([[-3.8730, 51.2299, -2.2650, 4.3458]])
        self.assertTrue(all(value.real < 0.0 for value in np.linalg.eigvals(a - b @ k)))
        self.assertTrue(any(value.real > 0.0 for value in np.linalg.eigvals(a + b @ k)))

    def test_centered_reference_experiment(self):
        engine = self.engine()
        engine.state["system::controller::targetArmAngleRadians"] = math.pi / 2.0
        max_pendulum = 0.0
        max_voltage = 0.0

        for _ in range(5000):
            engine.step(0.001)
            max_pendulum = max(
                max_pendulum,
                abs(resolve_value(
                    engine.state,
                    "system::plant::pendulumAngleFromUprightRadians",
                )),
            )
            max_voltage = max(
                max_voltage,
                abs(resolve_value(engine.state, "system::amplifier::executedVoltage")),
            )
            for requirement in self.parser.parsed_requirements:
                status = ExpressionEvaluator(
                    engine.state,
                    requirement.context,
                    self.parser.ref_bindings,
                    self.parser.system_part,
                    strict=True,
                ).evaluate(requirement.expression)
                self.assertIs(status, True, requirement.name)

        final_arm = resolve_value(engine.state, "system::plant::armAngleRadians")
        final_pendulum = resolve_value(
            engine.state, "system::plant::pendulumAngleFromUprightRadians"
        )
        self.assertAlmostEqual(final_arm, math.pi / 2.0, places=5)
        self.assertAlmostEqual(final_pendulum, 0.0, places=6)
        self.assertGreater(math.degrees(max_pendulum), 7.5)
        self.assertLess(math.degrees(max_pendulum), 9.0)
        self.assertGreater(max_voltage, 5.5)
        self.assertLess(max_voltage, 7.0)


if __name__ == "__main__":
    unittest.main()
