"""Staged regressions for the compact Hall-motor safety verifier."""

import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from hall_motor_verification import (  # noqa: E402
    MODEL,
    certify_structure,
    compile_contract,
    emit_smv,
    run,
)


FAKE_NUXMV = r'''#!/usr/bin/env python3
from pathlib import Path
import re
import sys

command_file = Path(sys.argv[sys.argv.index("-source") + 1])
command = command_file.read_text()
model_path = Path(re.search(r"read_model -i (.+)", command).group(1))
source = model_path.read_text()
count = len(re.findall(r"^INVARSPEC\b", source, re.MULTILINE))
if count != 1:
    print(f"expected exactly one isolated invariant, found {count}", file=sys.stderr)
    raise SystemExit(2)
print("-- invariant compact_motor_safety is true")
'''


class HallMotorVerificationTests(unittest.TestCase):
    @staticmethod
    def _fake_nuxmv(root: Path) -> Path:
        executable = root / "nuXmv"
        executable.write_text(FAKE_NUXMV)
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        return executable

    def test_solver_free_certificate_covers_exact_control_partition(self):
        contract = compile_contract(MODEL)
        certificate = certify_structure(contract)

        self.assertTrue(certificate["proved"])
        self.assertEqual(
            contract.current_projection_numerical_margin_amperes,
            0.000001,
        )
        self.assertEqual(len(certificate["checks"]), 21)
        self.assertIn(
            "physical pair current in the encoded forward-Euler process",
            certificate["scope"],
        )
        self.assertIn(
            "equivalence to NXP's unpublished dual-PI numerical configuration",
            certificate["explicit_non_claims"],
        )
        valid_cases = [
            check for check in certificate["checks"]
            if check["kind"] == "valid-hall-commutation"
        ]
        self.assertEqual(len(valid_cases), 12)

    def test_compact_smv_has_only_the_safety_slice(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            smv = emit_smv(compile_contract(MODEL), Path(directory) / "motor.smv")
            source = smv.read_text()

        self.assertEqual(
            len(re.findall(r"^INVARSPEC\b", source, re.MULTILINE)), 7)
        self.assertIn("projected_next_current", source)
        self.assertIn("safe_lower", source)
        self.assertNotIn("rotorMechanicalAngle", source)
        self.assertNotIn("secondsSinceLastHallEvent", source)

    def test_phase_table_drift_is_rejected_before_proof(self):
        source = MODEL.read_text()
        original = (
            "if executedSignedDutyFraction >= 0.0 and sampledHallCode == 6 {\n"
            "                    assign highSidePwmPhase := 3;\n"
            "                    assign lowSideOnPhase := 2;\n"
            "                    assign disconnectedPhase := 1;"
        )
        changed_text = (
            "if executedSignedDutyFraction >= 0.0 and sampledHallCode == 6 {\n"
            "                    assign highSidePwmPhase := 2;\n"
            "                    assign lowSideOnPhase := 2;\n"
            "                    assign disconnectedPhase := 1;"
        )
        self.assertEqual(source.count(original), 1)
        source = source.replace(original, changed_text, 1)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            changed = Path(directory) / "model.sysml"
            changed.write_text(source)
            with self.assertRaisesRegex(ValueError, "safety-slice digest"):
                compile_contract(changed)

    def test_projection_drift_is_rejected_before_proof(self):
        source = MODEL.read_text().replace(
            "configuredCurrentLimitAmperes -\n"
            "                    currentProjectionNumericalMarginAmperes -\n"
            "                    safetyObserverPairCurrentAmperes",
            "configuredCurrentLimitAmperes +\n"
            "                    currentProjectionNumericalMarginAmperes -\n"
            "                    safetyObserverPairCurrentAmperes",
            1,
        )
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            changed = Path(directory) / "model.sysml"
            changed.write_text(source)
            with self.assertRaisesRegex(ValueError, "safety-slice digest"):
                compile_contract(changed)

    def test_nuxmv_stage_runs_every_obligation_in_isolation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            report = run(
                MODEL,
                root / "run",
                nuxmv=self._fake_nuxmv(root),
                timeout_seconds=10,
            )

            self.assertTrue(report["verified"])
            self.assertTrue(report["structural_verified"])
            self.assertTrue(report["nuxmv_verified"])
            obligations = report["nuxmv"]["obligations"]
            self.assertEqual(len(obligations), 7)
            for obligation in obligations:
                self.assertEqual(obligation["status"], "proved")
                isolated = Path(obligation["smv"]).read_text()
                self.assertEqual(
                    len(re.findall(r"^INVARSPEC\b", isolated, re.MULTILINE)),
                    1,
                )

    def test_cli_solver_free_stage_completes_without_nuxmv(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            output = Path(directory) / "structural"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "hall_motor_verification.py"),
                 "--model", str(MODEL), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=20,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads((output / "verification.json").read_text())
            self.assertTrue(report["structural_verified"])
            self.assertIsNone(report["nuxmv_verified"])
            self.assertFalse(report["verified"])
            self.assertTrue((output / "motor-safety.smv").is_file())


if __name__ == "__main__":
    unittest.main()
