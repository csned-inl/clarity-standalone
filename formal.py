"""SysML-to-SMV extraction and nuXmv proof execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EXTRACTOR = ROOT / "sysml-models" / "mc-extract.py"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _prepare_nuxmv(nuxmv: Path, runtime_dir: Path) -> tuple[Path, dict[str, str], list[str]]:
    """Return an executable and environment safe for a bundled Linux nuXmv.

    The upstream binary archive ships both nuXmv's dependent libraries and a
    copy of glibc.  Adding that directory directly to ``LD_LIBRARY_PATH`` also
    replaces the host's libc/libm and can make the host C++ runtime impossible
    to load.  Build a small symlink view containing the bundled dependencies
    but not glibc, so the dynamic loader can safely combine the two.
    """
    executable = nuxmv.resolve()
    if executable.name == "nuXmv.sh" and (executable.parent / "nuXmv").is_file():
        executable = executable.parent / "nuXmv"

    environment = os.environ.copy()
    linked_libraries: list[str] = []
    if not sys.platform.startswith("linux"):
        return executable, environment, linked_libraries

    prefix = executable.parent.parent
    library_roots = [
        prefix / "lib" / "x86_64-linux-gnu",
        prefix / "lib64",
        prefix / "lib",
    ]
    library_root = next((path for path in library_roots
                         if (path / "libxml2.so.2").exists()), None)
    if library_root is None:
        return executable, environment, linked_libraries

    runtime_dir.mkdir(parents=True, exist_ok=True)
    unsafe_names = {"libc.so.6", "libm.so.6"}
    for source in sorted(library_root.glob("*.so*")):
        if source.name in unsafe_names or source.name.startswith("ld-linux"):
            continue
        destination = runtime_dir / source.name
        if destination.is_symlink() or destination.exists():
            destination.unlink()
        destination.symlink_to(source.resolve())
        linked_libraries.append(source.name)

    previous = environment.get("LD_LIBRARY_PATH")
    environment["LD_LIBRARY_PATH"] = (
        f"{runtime_dir}{os.pathsep}{previous}" if previous else str(runtime_dir)
    )
    return executable, environment, linked_libraries


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
    executable, environment, runtime_libraries = _prepare_nuxmv(
        nuxmv, out_dir / ".nuxmv-runtime-libs")
    try:
        checked = subprocess.run(
            [str(executable), "-source", str(commands.resolve())],
            cwd=out_dir, text=True, capture_output=True,
            env=environment,
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
        "nuXmv_executable": str(executable),
        "nuXmv_runtime_libraries": runtime_libraries,
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
