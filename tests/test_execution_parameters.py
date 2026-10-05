"""Regression tests for source-owned pipeline execution parameters."""

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sysml-models"))

from execution_parameters import load_execution_parameters  # noqa: E402
from simulator_adapter import SimulatorTwin  # noqa: E402


MODELS = ROOT / "sysml-models"


class ExecutionParameterTests(unittest.TestCase):
    def test_every_pipeline_model_has_one_source_owned_timing_contract(self):
        expected = {
            "thermostat": (1.0, 1, 1.0),
            "cruise-controller-model": (0.1, 1, 0.1),
            "mixing-sysml-model": (0.1, 1, 0.1),
            "rotary-inverted-pendulum": (0.001, 1, 0.001),
            "hall-sensored-bldc": (0.001, 20, 0.00005),
        }
        for directory, values in expected.items():
            with self.subTest(model=directory):
                execution = load_execution_parameters(
                    MODELS / directory / "model.sysml")
                self.assertEqual(
                    float(execution.controller_interval_seconds), values[0])
                self.assertEqual(execution.integration_substeps, values[1])
                self.assertEqual(execution.integration_step_float, values[2])

    def test_one_source_edit_changes_controller_and_integration_intervals(self):
        source_model = MODELS / "hall-sensored-bldc" / "model.sysml"
        source = source_model.read_text()
        source = source.replace(
            "controllerIntervalSeconds : Real = 0.001;",
            "controllerIntervalSeconds : Real = 0.01;",
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.sysml"
            model.write_text(source)
            execution = load_execution_parameters(model)
        self.assertEqual(float(execution.controller_interval_seconds), 0.01)
        self.assertEqual(execution.integration_substeps, 20)
        self.assertEqual(execution.integration_step_float, 0.0005)

    def test_explicit_integration_step_is_assertion_not_override(self):
        model = MODELS / "thermostat" / "model.sysml"
        with self.assertRaisesRegex(ValueError, "disagrees with SysML"):
            SimulatorTwin(str(model), dt=0.25)

    def test_generic_parameters_are_typed_and_fingerprinted(self):
        source = """
part def Example {
    #ExecutionParameter attribute controllerIntervalSeconds : Real = 0.5;
    #ExecutionParameter attribute integrationSubstepsPerControllerInterval : Integer = 2;
    #ExecutionParameter attribute solverIterations : Integer = 7;
    #ExecutionParameter attribute diagnosticsEnabled : Boolean = true;
}
"""
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.sysml"
            second = Path(directory) / "second.sysml"
            first.write_text(source)
            second.write_text(source.replace("solverIterations : Integer = 7",
                                             "solverIterations : Integer = 8"))
            a = load_execution_parameters(first)
            b = load_execution_parameters(second)
        self.assertEqual(a.values["solverIterations"], 7)
        self.assertIs(a.require_boolean("diagnosticsEnabled"), True)
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_duplicate_names_fail_closed(self):
        source = """
#ExecutionParameter attribute controllerIntervalSeconds : Real = 1.0;
#ExecutionParameter attribute controllerIntervalSeconds : Real = 2.0;
#ExecutionParameter attribute integrationSubstepsPerControllerInterval : Integer = 1;
"""
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.sysml"
            model.write_text(source)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                load_execution_parameters(model)

    def test_commented_declarations_are_not_configuration(self):
        source = """
// #ExecutionParameter attribute controllerIntervalSeconds : Real = 99.0;
/* #ExecutionParameter attribute solverIterations : Integer = 99; */
#ExecutionParameter attribute controllerIntervalSeconds : Real = 0.2;
#ExecutionParameter attribute integrationSubstepsPerControllerInterval : Integer = 2;
"""
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "model.sysml"
            model.write_text(source)
            execution = load_execution_parameters(model)
        self.assertEqual(execution.integration_step_float, 0.1)
        self.assertNotIn("solverIterations", execution.values)


if __name__ == "__main__":
    unittest.main()
