#!/usr/bin/env python3
"""Run one commit-pinned CLARITY job and publish a sanitized terminal report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workstation_reporting import (
    DEFAULT_REPOSITORY,
    ReportingError,
    build_report,
    confined_path,
    execute_logged,
    publish_report,
    repository_root,
    source_metadata,
    utc_now,
    validate_job_id,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--reports-checkout", type=Path)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not args.command:
        parser.error("supply the command to run after --")
    if not args.no_publish and args.reports_checkout is None:
        parser.error("--reports-checkout is required unless --no-publish is used")
    return args


def main() -> int:
    args = parse_args()
    try:
        job_id = validate_job_id(args.job_id)
        repo = repository_root(Path.cwd())
        source = source_metadata(repo, args.expected_sha, args.repository)
        result_root = confined_path(repo, args.result_root)
        job_dir = repo / "runs" / "workstation-jobs" / job_id
        if job_dir.exists():
            raise ReportingError(f"local job directory already exists: {job_dir}")
        job_dir.mkdir(parents=True)
        log_path = job_dir / "execution.log"
        started = utc_now()
        exit_code, interrupted = execute_logged(args.command, cwd=repo, log_path=log_path)
        finished = utc_now()
        report = build_report(
            job_id=job_id, source=source, command=args.command,
            started=started, finished=finished, exit_code=exit_code,
            interrupted_signal=interrupted, log_path=log_path, repo=repo,
            result_root=result_root)
        report_path = job_dir / "report.json"
        write_json(report_path, report)
        print(f"\nLocal report: {report_path}", flush=True)
        if args.no_publish:
            print("Publication skipped (--no-publish).", flush=True)
        else:
            try:
                commit = publish_report(
                    report_path, args.reports_checkout,
                    repository=args.repository)
                print(f"Published report commit: {commit}", flush=True)
            except ReportingError as exc:
                print(f"REPORT PUBLICATION FAILED: {exc}", file=sys.stderr, flush=True)
                print(
                    "Retry with:\n"
                    f"  {sys.executable} scripts/publish_workstation_result.py "
                    f"--report {report_path} --reports-checkout {args.reports_checkout}",
                    file=sys.stderr, flush=True)
                return 75
        return exit_code
    except ReportingError as exc:
        print(f"WORKSTATION JOB REFUSED: {exc}", file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())

