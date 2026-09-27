"""SysML-to-SMV extraction and nuXmv proof execution."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXTRACTOR = ROOT / "sysml-models" / "mc-extract.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(model: Path, out_dir: Path, *, dt: float, nuxmv: Path,
           timeout_seconds: int = 300) -> dict:
    """Generate a fresh SMV and require an IC3 result for every emitted spec."""
    out_dir.mkdir(parents=True, exist_ok=True)
    model = model.resolve()
    smv = out_dir / "model.smv"
    extract = subprocess.run(
        [sys.executable, str(EXTRACTOR), str(model), "--dt", str(dt),
         "-o", str(smv)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout_seconds,
    )
    (out_dir / "extract.log").write_text(extract.stdout + extract.stderr)
    if extract.returncode != 0 or not smv.is_file():
        raise RuntimeError(f"SysML-to-SMV extraction failed; see {out_dir / 'extract.log'}")

    source = smv.read_text()
    property_count = len(re.findall(r"^INVARSPEC\b", source, re.MULTILINE))
    requirement_names = re.findall(r"^-- Requirement: (.+)$", source, re.MULTILINE)
    if not property_count or not requirement_names:
        raise RuntimeError("extractor emitted no checkable safety requirements")

    commands = out_dir / "check_ic3.cmd"
    commands.write_text(f"read_model -i {smv.resolve()}\ngo_msat\ncheck_invar_ic3\nquit\n")
    try:
        checked = subprocess.run(
            [str(nuxmv.resolve()), "-source", str(commands.resolve())],
            cwd=out_dir, text=True, capture_output=True,
            timeout=timeout_seconds,
        )
        transcript = checked.stdout + checked.stderr
        returncode = checked.returncode
    except subprocess.TimeoutExpired as exc:
        transcript = (exc.stdout or b"").decode(errors="replace") if isinstance(
            exc.stdout, bytes) else (exc.stdout or "")
        transcript += "\nTIMEOUT\n"
        returncode = 124
    (out_dir / "nuxmv.txt").write_text(transcript)
    outcomes = re.findall(r"^-- invariant .*? is (true|false)\s*$",
                          transcript, re.MULTILINE)
    warnings = re.findall(r"^Warning: .+$", transcript, re.MULTILINE)
    report = {
        "model": str(model), "model_sha256": _sha256(model),
        "smv": str(smv.resolve()), "smv_sha256": _sha256(smv),
        "requirement_names": requirement_names,
        "emitted_invarspec_count": property_count,
        "nuXmv_result_count": len(outcomes),
        "nuXmv_results": outcomes,
        "nuXmv_returncode": returncode,
        "nuXmv_warnings": warnings,
        "verified": returncode == 0 and len(outcomes) == property_count
                    and all(result == "true" for result in outcomes),
        "transcript": str((out_dir / "nuxmv.txt").resolve()),
    }
    (out_dir / "verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    if not report["verified"]:
        raise RuntimeError(f"nuXmv did not prove every emitted invariant; see {out_dir}")
    return report
