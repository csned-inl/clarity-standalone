"""Fast method tests for the exact affine contraction certifier."""

from fractions import Fraction
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from affine_safety_certificate import (  # noqa: E402
    ScalarSafetyObjective,
    certify_scalar_affine_safety,
)
from symbolic_transition import AffineForm, AffineTransitionSystem  # noqa: E402


Q = Fraction


def system(multiplier: Q) -> AffineTransitionSystem:
    return AffineTransitionSystem(
        states=("x",),
        parameters=("r",),
        next_state={
            "x": AffineForm.build(Q(0), {
                "x": multiplier,
                "r": Q(1) - multiplier,
            }),
        },
        initial_state={"x": Q(0)},
        parameter_bounds={"r": (Q(-1), Q(1))},
        source_sha256="toy",
        mode_assumptions=("abs(x) < 2",),
    )


OBJECTIVE = ScalarSafetyObjective(
    parameter="r",
    safety_state="x",
    safety_bound=Q(2),
    mode_state="x",
    mode_bound=Q(2),
    prefix_steps=1,
    block_steps=1,
)


class AffineSafetyCertificateTests(unittest.TestCase):
    def test_contracting_affine_system_is_certified(self):
        report = certify_scalar_affine_safety(system(Q(1, 2)), OBJECTIVE)
        self.assertTrue(report["proved"])
        self.assertEqual(report["contraction_upper_bound"], 0.5)

    def test_noncontracting_system_is_not_certified(self):
        with self.assertRaisesRegex(ValueError, "equilibrium"):
            certify_scalar_affine_safety(system(Q(1)), OBJECTIVE)


if __name__ == "__main__":
    unittest.main()
