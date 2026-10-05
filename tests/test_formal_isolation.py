"""Regression tests for one-process-per-invariant formal verification."""

import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from formal import verify


MODEL = ROOT / "sysml-models/rotary-inverted-pendulum/model.sysml"


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
    print(f"expected one invariant, found {count}", file=sys.stderr)
    raise SystemExit(2)
print("-- invariant isolated is true")
'''

FAKE_NUXMV_WITH_FALSE = FAKE_NUXMV.replace(
    'print("-- invariant isolated is true")',
    '''
if "stay-within-balance-controller-envelope" in model_path.parent.name:
    print("-- invariant isolated is false")
else:
    print("-- invariant isolated is true")
''',
)

FAKE_NUXMV_WITH_TOOL_ERROR = FAKE_NUXMV.replace(
    'print("-- invariant isolated is true")',
    'print(\'file model.smv: line 1: "missing" undefined\\naborting "source check.cmd"\')',
)


class FormalIsolationTests(unittest.TestCase):
    @staticmethod
    def _executable(root: Path, source: str) -> Path:
        fake = root / "nuXmv"
        fake.write_text(source)
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        return fake

    def test_every_invariant_gets_an_independent_solver_invocation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            fake = self._executable(root, FAKE_NUXMV)
            report = verify(
                MODEL, root / "formal", dt=0.001, nuxmv=fake,
                timeout_seconds=10)

            self.assertTrue(report["verified"])
            self.assertEqual(report["requirement_count"], 3)
            self.assertGreaterEqual(report["emitted_invarspec_count"], 3)
            self.assertEqual(
                len(report["obligations"]),
                report["emitted_invarspec_count"],
            )
            for result in report["obligations"]:
                self.assertEqual(result["status"], "proved")
                source = Path(result["smv"]).read_text()
                self.assertEqual(source.count("INVARSPEC"), 1)
            persisted = json.loads(
                (root / "formal/verification.json").read_text())
            self.assertEqual(persisted["obligations"], report["obligations"])

    def test_one_failure_does_not_hide_other_obligation_results(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            fake = self._executable(root, FAKE_NUXMV_WITH_FALSE)
            report = verify(
                MODEL, root / "formal", dt=0.001, nuxmv=fake,
                timeout_seconds=10)

            self.assertFalse(report["verified"])
            self.assertEqual(
                len(report["obligations"]),
                report["emitted_invarspec_count"],
            )
            statuses = {
                result["name"]: result["status"]
                for result in report["obligations"]
                if result["kind"] == "requirement"
            }
            self.assertEqual(
                statuses["Stay Within Balance Controller Envelope"],
                "disproved",
            )
            self.assertEqual(statuses["Motor Voltage Within Authorized Range"],
                             "proved")
            self.assertEqual(statuses["Controller Supplies State Feedback"],
                             "proved")

    def test_zero_exit_tool_diagnostic_is_an_error_not_inconclusive(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            fake = self._executable(root, FAKE_NUXMV_WITH_TOOL_ERROR)
            report = verify(
                MODEL, root / "formal", dt=0.001, nuxmv=fake,
                timeout_seconds=10)

            self.assertFalse(report["verified"])
            self.assertTrue(all(
                result["status"] == "error"
                for result in report["obligations"]))
            self.assertTrue(all(
                result["nuXmv_errors"]
                for result in report["obligations"]))

    def test_named_direct_certificate_replaces_only_its_solver_obligation(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            fake = self._executable(root, FAKE_NUXMV_WITH_FALSE)
            calls = []

            def certificate(smv):
                calls.append(smv)
                return {"proved": True, "method": "test-certificate"}

            report = verify(
                MODEL, root / "formal", dt=0.001, nuxmv=fake,
                timeout_seconds=10,
                obligation_certifiers={
                    "Stay Within Balance Controller Envelope": certificate,
                },
            )

            self.assertTrue(report["verified"])
            self.assertEqual(len(calls), 1)
            result = next(
                item for item in report["obligations"]
                if item["name"] == "Stay Within Balance Controller Envelope")
            self.assertEqual(result["status"], "proved")
            self.assertEqual(result["method"], "direct-analytical-certificate")
            persisted = json.loads(Path(result["certificate"]).read_text())
            self.assertTrue(persisted["proved"])


if __name__ == "__main__":
    unittest.main()
