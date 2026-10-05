"""SysML-to-SMV extraction and isolated nuXmv proof execution."""

from __future__ import annotations

from dataclasses import dataclass
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


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value or "invariant"


@dataclass(frozen=True)
class Obligation:
    index: int
    name: str
    kind: str
    line_index: int
    source_line: str


def _invariant_obligations(source: str) -> list[Obligation]:
    """Identify every single-line INVARSPEC and its source requirement."""
    obligations: list[Obligation] = []
    pending_requirement: str | None = None
    for line_index, line in enumerate(source.splitlines()):
        stripped = line.strip()
        if stripped.startswith("-- Requirement:"):
            pending_requirement = stripped.split(":", 1)[1].strip()
            continue
        if stripped.startswith("INVARSPEC"):
            index = len(obligations) + 1
            if pending_requirement is None:
                name = f"Auxiliary invariant {index}"
                kind = "auxiliary"
            else:
                name = pending_requirement
                kind = "requirement"
            obligations.append(Obligation(
                index=index,
                name=name,
                kind=kind,
                line_index=line_index,
                source_line=line,
            ))
            pending_requirement = None
            continue
        if stripped and not stripped.startswith("--"):
            pending_requirement = None
    return obligations


def _isolated_source(source: str, selected: Obligation) -> str:
    """Return the same transition system with exactly one INVARSPEC."""
    lines = source.splitlines()
    for obligation in _invariant_obligations(source):
        if obligation.line_index != selected.line_index:
            lines[obligation.line_index] = (
                f"-- isolated-out obligation {obligation.index}")
    isolated = "\n".join(lines) + "\n"
    if len(re.findall(r"^INVARSPEC\b", isolated, re.MULTILINE)) != 1:
        raise RuntimeError("failed to isolate exactly one invariant")
    return isolated


def _run_obligation(obligation: Obligation, source: str, directory: Path,
                    nuxmv: Path, timeout_seconds: int) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    smv = directory / "model.smv"
    smv.write_text(_isolated_source(source, obligation))
    commands = directory / "check_ic3.cmd"
    commands.write_text(
        f"read_model -i {smv.resolve()}\n"
        "go_msat\n"
        "check_invar_ic3\n"
        "quit\n")
    try:
        checked = subprocess.run(
            [str(nuxmv.resolve()), "-source", str(commands.resolve())],
            cwd=directory, text=True, capture_output=True,
            timeout=timeout_seconds,
        )
        transcript = checked.stdout + checked.stderr
        returncode = checked.returncode
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(
            exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(
            exc.stderr, bytes) else (exc.stderr or "")
        transcript = stdout + stderr + "\nTIMEOUT\n"
        returncode = 124

    transcript_path = directory / "nuxmv.txt"
    transcript_path.write_text(transcript)
    outcomes = re.findall(
        r"^-- invariant .*? is (true|false)\s*$", transcript, re.MULTILINE)
    tool_errors = re.findall(
        r"(?:^|\n)(?:file .*?: line \d+: .* undefined|"
        r".*syntax error.*|.*aborting ['\"]source .*|Error: .*)",
        transcript,
        re.IGNORECASE,
    )
    if returncode == 124:
        status = "timeout"
    elif tool_errors:
        status = "error"
    elif outcomes == ["true"] and returncode == 0:
        status = "proved"
    elif outcomes == ["false"]:
        status = "disproved"
    elif returncode != 0:
        status = "error"
    else:
        status = "inconclusive"

    return {
        "index": obligation.index,
        "name": obligation.name,
        "kind": obligation.kind,
        "status": status,
        "nuXmv_returncode": returncode,
        "nuXmv_results": outcomes,
        "nuXmv_errors": tool_errors,
        "smv": str(smv.resolve()),
        "smv_sha256": _sha256(smv),
        "transcript": str(transcript_path.resolve()),
    }


def verify(model: Path, out_dir: Path, *, dt: float, nuxmv: Path,
           timeout_seconds: int = 300) -> dict:
    """Extract once and check every invariant in a separate nuXmv process.

    A timeout, counterexample, or tool error is recorded for that obligation
    and does not prevent the remaining obligations from running.  The return
    value is a certificate only when every emitted obligation is proved.
    """
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
        raise RuntimeError(
            f"SysML-to-SMV extraction failed; see {out_dir / 'extract.log'}")

    source = smv.read_text()
    obligations = _invariant_obligations(source)
    if not obligations:
        raise RuntimeError("extractor emitted no checkable invariant obligations")

    obligation_root = out_dir / "obligations"
    obligation_root.mkdir(exist_ok=False)
    results = []
    for obligation in obligations:
        directory = obligation_root / (
            f"{obligation.index:03d}-{_slug(obligation.name)}")
        results.append(_run_obligation(
            obligation, source, directory, nuxmv, timeout_seconds))

    requirement_results = [
        result for result in results if result["kind"] == "requirement"]
    verified = bool(results) and all(
        result["status"] == "proved" for result in results)
    report = {
        "model": str(model),
        "model_sha256": _sha256(model),
        "smv": str(smv.resolve()),
        "smv_sha256": _sha256(smv),
        "method": "isolated-check_invar_ic3",
        "timeout_seconds_per_obligation": timeout_seconds,
        "emitted_invarspec_count": len(obligations),
        "requirement_count": len(requirement_results),
        "obligations": results,
        "verified": verified,
    }
    (out_dir / "verification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report
