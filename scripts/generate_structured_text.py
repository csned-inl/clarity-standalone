#!/usr/bin/env python3
"""Generate an experimental Structured Text function block from a CLARITY policy."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from plc.structured_text import (  # noqa: E402
    INTEGER_TYPES,
    PLCGenerationError,
    generate_structured_text,
    write_structured_text_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--name", required=True, help="ST FUNCTION_BLOCK name")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--integer-type", choices=sorted(INTEGER_TYPES))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    manifest = args.manifest or args.output.with_suffix(".manifest.json")
    try:
        artifact = generate_structured_text(
            args.model,
            args.policy,
            function_block_name=args.name,
            integer_type=args.integer_type,
        )
        write_structured_text_artifact(
            artifact, args.output, manifest, overwrite=args.force)
    except (OSError, json.JSONDecodeError, PLCGenerationError) as exc:
        parser.error(str(exc))
    print(f"Structured Text: {args.output}")
    print(f"Manifest: {manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
