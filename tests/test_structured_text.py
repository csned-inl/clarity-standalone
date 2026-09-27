import copy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "sysml-models"), str(ROOT / "rl")]

from analytic import fit
from plc.structured_text import (
    PLCGenerationError,
    generate_structured_text,
    write_structured_text_artifact,
)


THERMOSTAT = ROOT / "sysml-models" / "thermostat" / "model.sysml"
MIXING = ROOT / "sysml-models" / "mixing-sysml-model" / "model.sysml"


class StructuredTextTests(unittest.TestCase):
    def test_thermostat_emits_deterministic_function_block_and_manifest(self):
        policy = fit(THERMOSTAT)
        first = generate_structured_text(
            THERMOSTAT, policy, function_block_name="CLARITY_ThermostatPolicy")
        second = generate_structured_text(
            THERMOSTAT, policy, function_block_name="CLARITY_ThermostatPolicy")
        self.assertEqual(first, second)
        self.assertIn("FUNCTION_BLOCK CLARITY_ThermostatPolicy", first.text)
        self.assertIn("setPoint : LREAL;", first.text)
        self.assertIn("done : BOOL;", first.text)
        self.assertIn(
            "heaterState := ((-1.0 + (1.0 * setPoint) + "
            "(-1.0 * temperatureCelcius)) >= 0.0);",
            first.text,
        )
        self.assertEqual(first.manifest["assignment_order"],
                         ["heaterState", "acState"])
        self.assertEqual(first.manifest["experiment"], "E001")
        self.assertEqual(len(first.manifest["structured_text_sha256"]), 64)

    def test_mixing_requires_explicit_bounded_integer_and_orders_dependencies(self):
        policy = fit(MIXING)
        with self.assertRaisesRegex(PLCGenerationError, "Integer is unbounded"):
            generate_structured_text(
                MIXING, policy, function_block_name="CLARITY_MixingPolicy")
        artifact = generate_structured_text(
            MIXING, policy, function_block_name="CLARITY_MixingPolicy",
            integer_type="DINT")
        self.assertIn("tank1VolumeMl : DINT;", artifact.text)
        self.assertIn(
            "((0 + (1 * tank1OriginalMl) + (-1 * tank1TargetTransferMl) + "
            "(-1 * tank1VolumeMl)) < 0)", artifact.text)
        self.assertNotIn("1.0 * tank1", artifact.text)
        order = artifact.manifest["assignment_order"]
        self.assertLess(order.index("shouldTurnOnPump1"),
                        order.index("shouldOpenValve1"))
        self.assertLess(order.index("shouldTurnOnPump2"),
                        order.index("shouldOpenValve2"))

    def test_rejects_source_hash_and_interface_changes(self):
        policy = fit(THERMOSTAT)
        bad_hash = copy.deepcopy(policy)
        bad_hash["source_model_sha256"] = "0" * 64
        with self.assertRaisesRegex(PLCGenerationError, "hash does not match"):
            generate_structured_text(
                THERMOSTAT, bad_hash,
                function_block_name="CLARITY_ThermostatPolicy")

        bad_inputs = copy.deepcopy(policy)
        bad_inputs["input_names"] = ["done", "setPoint"]
        with self.assertRaisesRegex(PLCGenerationError, "inputs do not exactly match"):
            generate_structured_text(
                THERMOSTAT, bad_inputs,
                function_block_name="CLARITY_ThermostatPolicy")

    def test_rejects_cycles_unknown_references_and_nonportable_names(self):
        policy = fit(THERMOSTAT)
        cyclic = copy.deepcopy(policy)
        cyclic["rules"]["heaterState"] = {
            "kind": "output", "name": "acState"}
        cyclic["rules"]["acState"] = {
            "kind": "output", "name": "heaterState"}
        with self.assertRaisesRegex(PLCGenerationError, "cyclic output"):
            generate_structured_text(
                THERMOSTAT, cyclic,
                function_block_name="CLARITY_ThermostatPolicy")
        with self.assertRaisesRegex(PLCGenerationError, "portable ST identifier"):
            generate_structured_text(
                THERMOSTAT, policy, function_block_name="FUNCTION_BLOCK")

    def test_artifact_writer_refuses_accidental_overwrite(self):
        artifact = generate_structured_text(
            THERMOSTAT, fit(THERMOSTAT),
            function_block_name="CLARITY_ThermostatPolicy")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "policy.st"
            manifest = Path(directory) / "policy.manifest.json"
            write_structured_text_artifact(artifact, output, manifest)
            self.assertEqual(output.read_text(), artifact.text)
            with self.assertRaisesRegex(PLCGenerationError, "refusing to overwrite"):
                write_structured_text_artifact(artifact, output, manifest)


if __name__ == "__main__":
    unittest.main()
