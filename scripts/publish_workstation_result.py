#!/usr/bin/env python3
"""Publish or retry one already-generated workstation report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from workstation_reporting import DEFAULT_REPOSITORY, ReportingError, publish_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--reports-checkout", type=Path, required=True)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    args = parser.parse_args()
    try:
        commit = publish_report(
            args.report, args.reports_checkout, repository=args.repository)
    except ReportingError as exc:
        print(f"REPORT PUBLICATION FAILED: {exc}", file=sys.stderr)
        return 75
    print(f"Published report commit: {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

