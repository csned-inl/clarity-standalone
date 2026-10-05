"""Non-PyTorch checks for the Hall-motor training shield."""

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "rl"))

from hall_motor_shield import HallMotorProjectionShield  # noqa: E402


class HallMotorTrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shield = HallMotorProjectionShield()

    def test_valid_hall_proposals_are_clipped_to_contract(self):
        self.assertEqual(self.shield.select(1.4, {"hallCode": 6}),
                         (1.0, True, 0.3999999999999999))
        self.assertEqual(self.shield.select(-1.4, {"hallCode": 1}),
                         (-1.0, True, 0.3999999999999999))
        self.assertEqual(self.shield.select(0.25, {"hallCode": 4}),
                         (0.25, False, 0.0))

    def test_invalid_hall_forces_zero_without_terminating_training(self):
        self.assertEqual(self.shield.select(0.75, {"hallCode": 0}),
                         (0.0, True, 0.75))
        self.assertEqual(self.shield.select(-0.25, {"hallCode": 7}),
                         (0.0, True, 0.25))

    def test_report_identifies_projection_not_unique_action(self):
        report = self.shield.report()
        self.assertEqual(report["contract_kind"],
                         "bounded_real_with_invalid_hall_zero")
        self.assertEqual(report["valid_hall_codes"], [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
