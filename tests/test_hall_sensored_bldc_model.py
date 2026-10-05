"""Source, structure, and numerical regressions for the pinned NXP motor."""

from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tmp_validation"))

from simulator import ExpressionEvaluator, SimulationEngine  # noqa: E402
from sysml_parser import SysMLParser  # noqa: E402


MODEL = ROOT / "sysml-models/hall-sensored-bldc/model.sysml"
README = MODEL.with_name("README.md")
AUDIT = MODEL.with_name("SOURCE_CONFORMANCE_AUDIT.md")


class HallSensoredBldcModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MODEL.read_text()
        cls.parser = SysMLParser(str(MODEL))
        cls.parser.parse()
        cls.engine = SimulationEngine(cls.parser)
        cls.engine.initialize()

    def test_reference_model_shape_and_wiring(self):
        self.assertEqual(self.parser.system_part, "system")
        self.assertEqual(
            self.parser.connects,
            [
                ("sensor.controllerPort", "controller.sensorPort"),
                ("sensor.commutatorPort", "drive.hallPort"),
                ("controller.proposalPort", "drive.proposalPort"),
            ],
        )
        self.assertEqual(len(self.parser.part_instances), 4)
        self.assertEqual(len(self.parser.parsed_requirements), 5)
        transitions = self.parser.instance_state_machines[
            "system::drive"
        ].transitions
        self.assertEqual(
            {transition.name for transition in transitions},
            {"above_duty_limit", "below_duty_limit", "inside_duty_limit"},
        )

    def test_exact_motor_and_bench_values_are_not_blended(self):
        expected = {
            "system::plant::phaseResistanceOhms": 0.192,
            "system::plant::dAxisInductanceHenries": 0.000096,
            "system::plant::qAxisInductanceHenries": 0.000107,
            "system::plant::backEmfConstantVoltSecondsPerRadian": 0.005872,
            "system::plant::torqueConstantNewtonMetersPerAmpere": 0.010614,
            "system::plant::rotorInertiaKilogramMetersSquared": 0.000012,
            "system::plant::polePairs": 2.0,
            "system::controller::configuredCurrentLimitAmperes": 6.0,
            "system::sensor::dcBusVoltageVolts": 12.0,
        }
        for key, value in expected.items():
            self.assertEqual(self.engine.state[key], value, key)

        # The 24 V motor nameplate and 12 V supplied bench operating point are
        # documented separately; the plant is not silently run at their mean.
        documentation = README.read_text()
        self.assertIn("24 V nameplate", documentation)
        self.assertIn("12 V bench supply", documentation)
        self.assertNotIn("18 V averaged", documentation)

    def test_physical_and_sampled_state_are_distinct(self):
        pairs = [
            (
                "system::plant::electricalSector",
                "system::sensor::sampledElectricalSector",
            ),
            (
                "system::plant::energizedPairCurrentAmperes",
                "system::sensor::sampledPairCurrentAmperes",
            ),
            (
                "system::plant::rotorMechanicalSpeedRadiansPerSecond",
                "system::sensor::estimatedMechanicalSpeedRadiansPerSecond",
            ),
            (
                "system::drive::proposedSignedDutyFraction",
                "system::drive::executedSignedDutyFraction",
            ),
        ]
        for physical, observed in pairs:
            self.assertIn(physical, self.engine.state)
            self.assertIn(observed, self.engine.state)
            self.assertNotEqual(physical, observed)

    def test_exact_sunrise_hall_sequence_is_present(self):
        expected = {
            0: (True, True, False, 6),
            1: (True, False, False, 4),
            2: (True, False, True, 5),
            3: (False, False, True, 1),
            4: (False, True, True, 3),
            5: (False, True, False, 2),
        }
        for sector, (hall_a, hall_b, hall_c, code) in expected.items():
            hall_a_text = str(hall_a).lower()
            hall_b_text = str(hall_b).lower()
            hall_c_text = str(hall_c).lower()
            pattern = re.compile(
                rf"if sampledElectricalSector == {sector} \{{.*?"
                rf"assign hallA := {hall_a_text};.*?"
                rf"assign hallB := {hall_b_text};.*?"
                rf"assign hallC := {hall_c_text};.*?"
                rf"assign hallCode := {code};",
                re.DOTALL,
            )
            self.assertRegex(self.source, pattern)

    def test_forward_and_reverse_wrap_are_mutually_exclusive(self):
        self.assertIn(
            "sampledElectricalSector == previousElectricalSector + 1 or",
            self.source,
        )
        self.assertIn(
            "previousElectricalSector == sampledElectricalSector + 1 or",
            self.source,
        )
        # A raw numeric >/< comparison misclassifies the 5->0 and 0->5 wraps
        # in both directions and can reset the Hall timer twice in one step.
        self.assertNotIn(
            "sampledElectricalSector > previousElectricalSector or",
            self.source,
        )
        self.assertNotIn(
            "sampledElectricalSector < previousElectricalSector or",
            self.source,
        )

    def test_speed_estimator_uses_six_direction_consistent_periods(self):
        self.assertIn(
            "periods.currentPeriodSeconds +\n"
            "                              periods.period1Seconds + periods.period2Seconds +\n"
            "                              periods.period3Seconds + periods.period4Seconds +\n"
            "                              periods.period5Seconds",
            self.source,
        )
        self.assertIn("attribute lastTransitionDirection : Integer;", self.source)
        self.assertIn("assign validCommutationPeriodCount := 1;", self.source)
        self.assertNotIn(
            "electricalSectorWidthRadians /\n"
            "                        (polePairs * secondsSinceLastHallEvent)",
            self.source,
        )

        engine = SimulationEngine(self.parser)
        engine.initialize()
        engine.model = lambda _inputs: {"proposedSignedDutyFraction": 0.0}
        for sector in (1, 2, 3, 4, 5, 0):
            engine.state["system::plant::electricalSector"] = sector
            engine.step(0.00005)
        self.assertEqual(
            engine.state["system::sensor::validCommutationPeriodCount"], 6
        )
        self.assertAlmostEqual(
            engine.state[
                "system::sensor::estimatedMechanicalSpeedRadiansPerSecond"
            ],
            6.0 * 1.047197551197 / (2.0 * 6.0 * 0.00005),
            places=6,
        )

        # A reversal begins a fresh direction-consistent window; it must not
        # average the previous forward intervals into a reverse speed.
        engine.state["system::plant::electricalSector"] = 5
        engine.step(0.00005)
        self.assertEqual(engine.state["system::sensor::lastTransitionDirection"], -1)
        self.assertEqual(
            engine.state["system::sensor::validCommutationPeriodCount"], 1
        )
        self.assertEqual(
            engine.state[
                "system::sensor::estimatedMechanicalSpeedRadiansPerSecond"
            ],
            0.0,
        )

    def test_unsourced_plant_reduction_is_explicit(self):
        expected = {
            "system::plant::effectivePairResistanceOhms": 0.384,
            "system::plant::effectivePairInductanceHenries": 0.000214,
            "system::plant::effectivePairBackEmfConstantVoltSecondsPerRadian": 0.011744,
            "system::plant::effectiveTorqueConstantNewtonMetersPerAmpere": 0.010614,
            "system::plant::effectiveBenchInertiaKilogramMetersSquared": 0.000012,
            "system::plant::externalLoadTorqueNewtonMeters": 0.0,
            "system::plant::unmodeledLossTorqueNewtonMeters": 0.0,
        }
        for key, value in expected.items():
            self.assertEqual(self.engine.state[key], value, key)

        for name in (
            "effectivePairResistanceOhms",
            "effectivePairInductanceHenries",
            "effectivePairBackEmfConstantVoltSecondsPerRadian",
            "effectiveTorqueConstantNewtonMetersPerAmpere",
            "effectiveBenchInertiaKilogramMetersSquared",
            "externalLoadTorqueNewtonMeters",
            "unmodeledLossTorqueNewtonMeters",
        ):
            self.assertRegex(
                self.source,
                rf"#ModelAssumption attribute {name} : Real;",
            )

    def test_current_limit_replacement_is_controller_rate_and_not_drive_logic(self):
        drive = self.source.split("part def HallCommutatedDrive", 1)[1].split(
            "part def SpeedController", 1
        )[0]
        controller = self.source.split("part def SpeedController", 1)[1].split(
            "part def HallSensoredBrushlessMotorSystem", 1
        )[0]
        self.assertNotIn("currentLimitAmperes", drive)
        self.assertIn("configuredCurrentLimitAmperes", controller)
        self.assertIn("Current Limit Surrogate", self.source)
        self.assertIn("speedControlTickCount >= speedControlTicksPerUpdate - 1", controller)

        engine = SimulationEngine(self.parser)
        engine.initialize()
        engine.model = lambda _inputs: {"proposedSignedDutyFraction": 0.5}
        engine.state["system::sensor::currentMeasurementErrorAmperes"] = 10.0
        for _ in range(20):
            engine.step(0.00005)
        self.assertEqual(
            engine.state[
                "system::controller::lastCurrentLimitedSignedDutyFraction"
            ],
            0.0,
        )
        self.assertEqual(
            engine.state["system::drive::boundedProposedSignedDutyFraction"],
            0.0,
        )

    def test_missing_data_impact_and_certificate_boundary_are_documented(self):
        audit = AUDIT.read_text()
        for phrase in (
            "no hardware rise-time claim",
            "no switching-level voltage/current theorem",
            "no thermal claim",
            "RUN-phase claim only",
            "certificate for the NXP hardware, reference firmware",
        ):
            self.assertIn(phrase, audit)

    def test_current_surrogate_is_not_a_physical_six_ampere_invariant(self):
        engine = SimulationEngine(self.parser)
        engine.initialize()
        engine.model = lambda _inputs: {"proposedSignedDutyFraction": 1.0}
        peak_current = 0.0
        for _ in range(40):
            engine.step(0.00005)
            peak_current = max(
                peak_current,
                abs(engine.state["system::plant::energizedPairCurrentAmperes"]),
            )
        self.assertGreater(peak_current, 6.0)
        self.assertIn(
            "cannot:\n\n- reproduce PI response",
            AUDIT.read_text(),
        )

    def test_model_contains_nonsemantic_source_provenance(self):
        self.assertIn("SOURCE PROVENANCE -- comments only", self.source)
        self.assertIn("S32M244 - Hall sensor based 6-step BLDC motor control", self.source)
        self.assertIn("M1_params_Sunrise95.txt", self.source)
        self.assertIn("AN12435.pdf", self.source)

    def test_exact_nxp_phase_table_is_complete(self):
        # phase tuple is (high-side PWM, low-side ON, disconnected)
        ccw = {
            6: (3, 2, 1),
            4: (3, 1, 2),
            5: (2, 1, 3),
            1: (2, 3, 1),
            3: (1, 3, 2),
            2: (1, 2, 3),
        }
        cw = {
            6: (2, 3, 1),
            2: (2, 1, 3),
            3: (3, 1, 2),
            1: (3, 2, 1),
            5: (1, 2, 3),
            4: (1, 3, 2),
        }
        for relation, table in ((">= 0.0", ccw), ("< 0.0", cw)):
            for hall, phases in table.items():
                high, low, disconnected = phases
                pattern = re.compile(
                    rf"executedSignedDutyFraction {re.escape(relation)} and "
                    rf"sampledHallCode == {hall} \{{.*?"
                    rf"highSidePwmPhase := {high};.*?"
                    rf"lowSideOnPhase := {low};.*?"
                    rf"disconnectedPhase := {disconnected};",
                    re.DOTALL,
                )
                self.assertRegex(self.source, pattern)

    def test_two_documented_rates_are_exactly_related(self):
        commutation_period = self.engine.state[
            "system::plant::commutationSamplePeriodSeconds"
        ]
        ticks = self.engine.state[
            "system::controller::speedControlTicksPerUpdate"
        ]
        self.assertEqual(commutation_period, 0.00005)
        self.assertEqual(ticks, 20.0)
        self.assertAlmostEqual(commutation_period * ticks, 0.001, places=15)

        nameplate_speed = 9000.0 * 2.0 * 3.141592653589793 / 60.0
        max_electrical_step = 2.0 * nameplate_speed * commutation_period
        sector_width = self.engine.state[
            "system::plant::electricalSectorWidthRadians"
        ]
        self.assertLess(max_electrical_step, sector_width)

    def test_multirate_run_phase_smoke_preserves_declared_requirements(self):
        engine = SimulationEngine(self.parser)
        engine.initialize()
        engine.model = lambda _inputs: {"proposedSignedDutyFraction": 0.25}

        # Twenty milliseconds crosses controller updates, current limiting,
        # rotor motion, and Hall-sector updates. This is a regression smoke
        # check, not a continuous-time or hardware-validation proof.
        for _ in range(400):
            engine.step(0.00005)
            for requirement in self.parser.parsed_requirements:
                status = ExpressionEvaluator(
                    engine.state,
                    requirement.context,
                    self.parser.ref_bindings,
                    self.parser.system_part,
                    strict=True,
                ).evaluate(requirement.expression)
                self.assertIs(status, True, requirement.name)

        self.assertGreater(
            engine.state["system::plant::rotorMechanicalSpeedRadiansPerSecond"],
            0.0,
        )
        self.assertIn(
            int(engine.state["system::sensor::hallCode"]),
            {1, 2, 3, 4, 5, 6},
        )

    def test_other_application_controller_values_are_not_imported(self):
        # These exact values exist in NXP's FOC application parameter file but
        # are board/application settings, not intrinsic Sunrise motor data.
        for excluded in (
            "0.0544",  # FOC speed-loop proportional gain
            "0.002",   # FOC speed-loop integral gain
            "645.2",   # FOC application temperature scale
            "31.25",   # FOC application current base
        ):
            self.assertNotIn(excluded, self.source)


if __name__ == "__main__":
    unittest.main()
