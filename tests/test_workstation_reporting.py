#!/usr/bin/env python3
"""Regression tests for the workstation execution/reporting channel."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from workstation_reporting import (  # noqa: E402
    build_report,
    collect_clarity_results,
    execute_logged,
    publish_report,
    redact_text,
    write_json,
)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


class WorkstationReportingTests(unittest.TestCase):
    def test_execute_logged_success_failure_and_missing_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            success_log = root / "success.log"
            status, interrupted = execute_logged(
                [sys.executable, "-c", "print('handshake-ok')"],
                cwd=root, log_path=success_log)
            self.assertEqual((status, interrupted), (0, None))
            self.assertEqual(success_log.read_text(), "handshake-ok\n")

            failure_log = root / "failure.log"
            status, interrupted = execute_logged(
                [sys.executable, "-c", "print('expected-failure'); raise SystemExit(7)"],
                cwd=root, log_path=failure_log)
            self.assertEqual((status, interrupted), (7, None))
            self.assertIn("expected-failure", failure_log.read_text())

            missing_log = root / "missing.log"
            status, interrupted = execute_logged(
                [str(root / "not-a-command")], cwd=root, log_path=missing_log)
            self.assertEqual((status, interrupted), (127, None))
            self.assertIn("FileNotFoundError", missing_log.read_text())

    def test_redaction_removes_paths_and_common_tokens(self):
        repo = Path("/home/person/src/repository")
        home = Path("/home/person")
        text = (
            "/home/person/src/repository/run "
            "token=ghp_abcdefghijklmnopqrstuvwxyz012345 "
            "https://user:password@example.test/path")
        redacted = redact_text(text, repo=repo, home=home)
        self.assertIn("$REPO/run", redacted)
        self.assertNotIn("/home/person", redacted)
        self.assertNotIn("ghp_", redacted)
        self.assertNotIn("user:password", redacted)

    def test_collects_allowlisted_clarity_fields_without_paths(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "thermostat" / "analytic"
            target.mkdir(parents=True)
            (target / "summary.json").write_text(json.dumps({
                "model": "thermostat",
                "method": "analytic",
                "dt_seconds": 1.0,
                "model_sha256": "a" * 64,
                "formal_verified": True,
                "formal_report": "/secret/home/formal.json",
                "shield": {"action_count": 4, "valid_actions": 3,
                           "dead_actions": [3]},
                "policy": {
                    "method": "analytical_affine_predicate_fit",
                    "final_model": "/secret/home/policy.json",
                    "evaluation": {"successes": 10,
                                   "safety_violation_episodes": 0,
                                   "total_steps": 123},
                },
            }))
            collected = collect_clarity_results(root)
            encoded = json.dumps(collected)
            self.assertEqual(collected[0]["model"], "thermostat")
            self.assertEqual(collected[0]["policy"]["evaluation"]["successes"], 10)
            self.assertNotIn("/secret/home", encoded)
            self.assertNotIn("final_model", encoded)
            self.assertNotIn("formal_report", encoded)

    def test_build_report_publishes_only_failure_excerpt(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            log = repo / "execution.log"
            log.write_text(f"failure under {repo}\n")
            result_root = repo / "results"
            result_root.mkdir()
            moment = datetime(2026, 9, 27, tzinfo=timezone.utc)
            source = {"repository": "test/repo", "branch": "test",
                      "commit": "a" * 40, "tracked_tree_clean": True}
            report = build_report(
                job_id="failure-test", source=source,
                command=[sys.executable, "-c", "raise SystemExit(4)"],
                started=moment, finished=moment, exit_code=4,
                interrupted_signal=None, log_path=log, repo=repo,
                result_root=result_root)
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["exit_code"], 4)
            self.assertIn("$REPO", report["failure_excerpt"][0])
            self.assertFalse(report["local_log"]["published"])

    def test_publish_report_commits_and_pushes_to_fake_remote(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            seed = root / "seed"
            checkout = root / "reports"
            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(seed))
            git(seed, "config", "user.name", "Test User")
            git(seed, "config", "user.email", "test@example.invalid")
            git(seed, "switch", "-c", "workstation-results")
            (seed / "README.md").write_text("report channel\n")
            (seed / ".gitignore").write_text("runs/\n")
            git(seed, "add", "README.md", ".gitignore")
            git(seed, "commit", "-m", "Initialize reports")
            git(seed, "push", "-u", "origin", "workstation-results")
            git(root, "clone", "--branch", "workstation-results", str(remote), str(checkout))
            git(checkout, "config", "user.name", "Test User")
            git(checkout, "config", "user.email", "test@example.invalid")

            report = {
                "schema_version": 1,
                "project": "CLARITY",
                "run_id": "handshake-test",
                "status": "passed",
                "source": {"repository": "test/repo"},
            }
            report_path = root / "report.json"
            write_json(report_path, report)
            commit = publish_report(
                report_path, checkout, repository="test/repo",
                verify_remote=False)

            self.assertEqual(commit, git(checkout, "rev-parse", "HEAD"))
            published = checkout / "workstation-reports" / "results" / "handshake-test.json"
            self.assertTrue(published.is_file())
            self.assertEqual(json.loads(published.read_text())["status"], "passed")
            self.assertEqual(
                git(checkout, "status", "--porcelain"), "")

    def test_publish_recovers_known_partial_legacy_add(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote.git"
            seed = root / "seed"
            checkout = root / "reports"
            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(seed))
            git(seed, "config", "user.name", "Test User")
            git(seed, "config", "user.email", "test@example.invalid")
            git(seed, "switch", "-c", "workstation-results")
            (seed / ".gitignore").write_text("runs/\n")
            (seed / "README.md").write_text("report channel\n")
            git(seed, "add", ".gitignore", "README.md")
            git(seed, "commit", "-m", "Initialize reports")
            git(seed, "push", "-u", "origin", "workstation-results")
            git(root, "clone", "--branch", "workstation-results", str(remote), str(checkout))
            git(checkout, "config", "user.name", "Test User")
            git(checkout, "config", "user.email", "test@example.invalid")

            report = {
                "schema_version": 1,
                "project": "CLARITY",
                "run_id": "legacy-partial",
                "status": "passed",
                "source": {"repository": "test/repo"},
            }
            report_path = root / "report.json"
            write_json(report_path, report)
            canonical = report_path.read_text()
            latest = checkout / "workstation-reports" / "latest.json"
            legacy = checkout / "workstation-reports" / "runs" / "legacy-partial.json"
            latest.parent.mkdir(parents=True)
            legacy.parent.mkdir(parents=True)
            latest.write_text(canonical)
            legacy.write_text(canonical)
            git(checkout, "add", "workstation-reports/latest.json")

            publish_report(
                report_path, checkout, repository="test/repo",
                verify_remote=False)

            self.assertFalse(legacy.exists())
            self.assertTrue((checkout / "workstation-reports" / "results" /
                             "legacy-partial.json").is_file())
            self.assertEqual(git(checkout, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
