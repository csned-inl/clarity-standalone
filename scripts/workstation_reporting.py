"""Local execution and sanitized Git reporting for CLARITY workstation jobs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


SCHEMA_VERSION = 1
DEFAULT_REPOSITORY = "csned-inl/clarity-standalone"
DEFAULT_REPORT_BRANCH = "workstation-results"
JOB_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,79}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(r"(?i)\b(password|passwd|token|secret)\s*[=:]\s*\S+"),
    re.compile(r"(https?://)[^/@\s:]+:[^/@\s]+@"),
)
EVALUATION_KEYS = (
    "episodes_requested", "episodes_completed", "successes", "task_errors",
    "task_error_rate", "safety_violation_episodes", "evaluation_errors",
    "pointwise_rule_disagreements", "total_steps", "shield_overrides",
    "shield_override_rate", "failed_requirement_checks", "error_messages",
)
TRAINING_KEYS = (
    "architecture", "oracle_samples", "oracle_epochs", "ppo_episodes",
    "checkpoint_interval", "observation_dimension", "action_count",
    "parameter_count", "device", "seed", "dt_seconds",
)


class ReportingError(RuntimeError):
    """A safe, user-actionable reporting failure."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def validate_job_id(value: str) -> str:
    if not JOB_ID_RE.fullmatch(value):
        raise ReportingError("job ID must match [a-z0-9][a-z0-9._-]{0,79}")
    return value


def validate_sha(value: str) -> str:
    value = value.lower()
    if not SHA_RE.fullmatch(value):
        raise ReportingError("expected SHA must be exactly 40 lowercase hexadecimal characters")
    return value


def run_command(args: Sequence[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        list(args), cwd=cwd, text=True, capture_output=True, errors="replace")
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise ReportingError(f"command failed ({shlex.join(args)}): {detail}")
    return result


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run_command(("git", *args), cwd=repo, check=check)


def repository_root(start: Path) -> Path:
    result = git(start, "rev-parse", "--show-toplevel")
    return Path(result.stdout.strip()).resolve()


def _remote_matches(remote: str, repository: str) -> bool:
    normalized = remote.strip().removesuffix(".git").removesuffix("/")
    return normalized.endswith(f"github.com/{repository}")


def source_metadata(repo: Path, expected_sha: str, repository: str) -> dict[str, Any]:
    expected_sha = validate_sha(expected_sha)
    actual_sha = git(repo, "rev-parse", "HEAD").stdout.strip().lower()
    if actual_sha != expected_sha:
        raise ReportingError(
            f"source commit mismatch: expected {expected_sha}, found {actual_sha}")
    dirty = git(repo, "status", "--porcelain", "--untracked-files=no").stdout.strip()
    if dirty:
        raise ReportingError("tracked source files are dirty; commit or restore them before running")
    remote = git(repo, "remote", "get-url", "origin").stdout.strip()
    if not _remote_matches(remote, repository):
        raise ReportingError(f"origin is not the expected GitHub repository: {remote}")
    branch = git(repo, "symbolic-ref", "--short", "-q", "HEAD", check=False).stdout.strip()
    return {
        "repository": repository,
        "branch": branch or "DETACHED",
        "commit": actual_sha,
        "tracked_tree_clean": True,
    }


def confined_path(repo: Path, candidate: Path) -> Path:
    resolved = candidate if candidate.is_absolute() else repo / candidate
    resolved = resolved.resolve(strict=False)
    try:
        resolved.relative_to(repo)
    except ValueError as exc:
        raise ReportingError(f"path must remain inside the source repository: {candidate}") from exc
    return resolved


def redact_text(text: str, *, repo: Path | None = None, home: Path | None = None) -> str:
    if repo:
        text = text.replace(str(repo), "$REPO")
    if home:
        text = text.replace(str(home), "$HOME")
    for pattern in TOKEN_PATTERNS:
        if pattern.pattern.startswith("(https?"):
            text = pattern.sub(r"\1[REDACTED]@", text)
        elif "bearer" in pattern.pattern.lower():
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path, root: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ReportingError(f"artifact escaped result root: {path}") from exc
    if path.is_symlink() or path.stat().st_size > 1024 * 1024:
        raise ReportingError(f"refusing unsafe or oversized JSON artifact: {path}")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ReportingError(f"expected a JSON object: {path}")
    return value


def _select(mapping: Any, keys: Sequence[str]) -> dict[str, Any]:
    if not isinstance(mapping, dict):
        return {}
    return {key: mapping[key] for key in keys if key in mapping}


def _evaluation(mapping: Any) -> dict[str, Any]:
    return _select(mapping, EVALUATION_KEYS)


def _checkpoint_report(mapping: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "selection_rule": mapping.get("selection_rule"),
        "ranked_checkpoints": mapping.get("ranked_checkpoints", []),
        "selected": None,
    }
    selected = mapping.get("selected")
    if isinstance(selected, dict):
        result["selected"] = {
            "checkpoint": selected.get("checkpoint"),
            **_evaluation(selected),
        }
    if isinstance(mapping.get("held_out_test"), dict):
        result["held_out_test"] = _evaluation(mapping["held_out_test"])
    if isinstance(mapping.get("training"), dict):
        result["training"] = _select(mapping["training"], TRAINING_KEYS)
    return result


def collect_clarity_results(result_root: Path) -> list[dict[str, Any]]:
    if not result_root.exists():
        return []
    if result_root.is_symlink() or not result_root.is_dir():
        raise ReportingError("result root must be a real directory")
    reports: list[dict[str, Any]] = []
    for path in sorted(result_root.rglob("summary.json")):
        summary = _read_json(path, result_root)
        row: dict[str, Any] = {
            "artifact": str(path.relative_to(result_root)),
            "model": summary.get("model"),
            "method": summary.get("method"),
            "dt_seconds": summary.get("dt_seconds"),
            "model_sha256": summary.get("model_sha256"),
            "formal_verified": summary.get("formal_verified"),
            "shield": _select(summary.get("shield"), (
                "action_count", "valid_actions", "dead_actions",
                "input_names", "output_names")),
        }
        policy = summary.get("policy")
        if isinstance(policy, dict):
            if summary.get("method") == "analytic":
                row["policy"] = {
                    "method": policy.get("method"),
                    "evaluation": _evaluation(policy.get("evaluation")),
                }
            else:
                row["policy"] = _checkpoint_report(policy)
        reports.append(row)

    summarized_dirs = {path.parent for path in result_root.rglob("summary.json")}
    for path in sorted(result_root.rglob("checkpoint_selection.json")):
        if path.parent in summarized_dirs:
            continue
        reports.append({
            "artifact": str(path.relative_to(result_root)),
            "partial_checkpoint_selection": _checkpoint_report(_read_json(path, result_root)),
        })
    for path in sorted(result_root.rglob("verification.json")):
        if path.parent.parent in summarized_dirs:
            continue
        verification = _read_json(path, result_root)
        reports.append({
            "artifact": str(path.relative_to(result_root)),
            "partial_formal_verification": _select(verification, (
                "model_sha256", "smv_sha256", "requirement_names",
                "emitted_invarspec_count", "nuXmv_result_count",
                "nuXmv_results", "nuXmv_returncode", "verified")),
        })
    return reports


def runtime_metadata() -> dict[str, Any]:
    result: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    try:
        import torch

        result.update({
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "cuda_available": bool(torch.cuda.is_available()),
            "cuda_device_count": int(torch.cuda.device_count()),
        })
        if torch.cuda.is_available():
            result["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception as exc:
        result.update({
            "torch_available": False,
            "torch_probe_error": type(exc).__name__,
        })
    return result


def failure_excerpt(log_path: Path, *, repo: Path, line_limit: int = 80,
                    byte_limit: int = 16 * 1024) -> list[str]:
    if not log_path.is_file():
        return []
    with log_path.open("rb") as stream:
        size = stream.seek(0, os.SEEK_END)
        stream.seek(max(0, size - byte_limit))
        text = stream.read().decode(errors="replace")
    lines = text.splitlines()[-line_limit:]
    home = Path.home().resolve()
    return [redact_text(line, repo=repo, home=home) for line in lines]


def build_report(*, job_id: str, source: dict[str, Any], command: Sequence[str],
                 started: datetime, finished: datetime, exit_code: int,
                 interrupted_signal: int | None, log_path: Path,
                 repo: Path, result_root: Path) -> dict[str, Any]:
    validate_job_id(job_id)
    status = "interrupted" if interrupted_signal else ("passed" if exit_code == 0 else "failed")
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project": "CLARITY",
        "run_id": job_id,
        "status": status,
        "exit_code": exit_code,
        "interrupted_signal": interrupted_signal,
        "started_at_utc": iso_utc(started),
        "finished_at_utc": iso_utc(finished),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "source": source,
        "command": redact_text(shlex.join(command), repo=repo, home=Path.home().resolve()),
        "runtime": runtime_metadata(),
        "clarity_results": collect_clarity_results(result_root),
        "local_log": {
            "sha256": sha256_file(log_path),
            "bytes": log_path.stat().st_size,
            "published": False,
        },
    }
    if exit_code != 0:
        report["failure_excerpt"] = failure_excerpt(log_path, repo=repo)
    return report


def execute_logged(command: Sequence[str], *, cwd: Path, log_path: Path) -> tuple[int, int | None]:
    if not command:
        raise ReportingError("no command was supplied after --")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    interrupted: int | None = None
    process: subprocess.Popen[str] | None = None
    prior_handlers: dict[int, Any] = {}

    def forward(signum: int, _frame: Any) -> None:
        nonlocal interrupted
        interrupted = signum
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    for signum in (signal.SIGINT, signal.SIGTERM):
        prior_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, forward)
    try:
        with log_path.open("w", encoding="utf-8") as log:
            try:
                process = subprocess.Popen(
                    list(command), cwd=cwd, text=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, errors="replace", bufsize=1,
                    start_new_session=True)
            except OSError as exc:
                message = f"{type(exc).__name__}: {exc}\n"
                sys.stdout.write(message)
                log.write(message)
                return 127, None
            assert process.stdout is not None
            with process.stdout:
                for line in process.stdout:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log.write(line)
                    log.flush()
            returncode = process.wait()
    finally:
        for signum, handler in prior_handlers.items():
            signal.signal(signum, handler)
    if interrupted and returncode < 0:
        return 128 + interrupted, interrupted
    return returncode, interrupted


def _git_dir(checkout: Path) -> Path:
    value = git(checkout, "rev-parse", "--git-dir").stdout.strip()
    path = Path(value)
    return (checkout / path).resolve() if not path.is_absolute() else path.resolve()


def _load_report(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ReportingError("report does not use the supported schema version")
    validate_job_id(str(value.get("run_id", "")))
    if value.get("status") not in {"passed", "failed", "interrupted"}:
        raise ReportingError("report has an invalid status")
    return value


def publish_report(report_path: Path, checkout: Path, *,
                   repository: str = DEFAULT_REPOSITORY,
                   branch: str = DEFAULT_REPORT_BRANCH,
                   verify_remote: bool = True) -> str:
    report_path = report_path.resolve()
    checkout = checkout.resolve()
    report = _load_report(report_path)
    if repository != report.get("source", {}).get("repository"):
        raise ReportingError("report repository does not match publication target")
    if repository != DEFAULT_REPOSITORY and verify_remote:
        raise ReportingError("non-default repository requires explicit test mode")
    if not checkout.is_dir():
        raise ReportingError(f"reporting checkout does not exist: {checkout}")
    current_branch = git(checkout, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if current_branch != branch:
        raise ReportingError(f"reporting checkout must be on {branch}, found {current_branch}")
    remote = git(checkout, "remote", "get-url", "origin").stdout.strip()
    if verify_remote and not _remote_matches(remote, repository):
        raise ReportingError(f"reporting origin is not {repository}: {remote}")
    if git(checkout, "status", "--porcelain").stdout.strip():
        raise ReportingError("reporting checkout has uncommitted changes")

    lock_path = _git_dir(checkout) / "workstation-report.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        git(checkout, "pull", "--rebase", "origin", branch)

        relative = Path("workstation-reports") / "runs" / f"{report['run_id']}.json"
        destination = checkout / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        canonical = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if destination.exists():
            if destination.read_text() != canonical:
                raise ReportingError(f"run ID already exists with different content: {report['run_id']}")
            git(checkout, "push", "origin", branch)
            return git(checkout, "rev-parse", "HEAD").stdout.strip()

        name = git(checkout, "config", "user.name", check=False).stdout.strip()
        email = git(checkout, "config", "user.email", check=False).stdout.strip()
        if not name or not email:
            raise ReportingError("configure git user.name and user.email in the reporting checkout")
        destination.write_text(canonical)
        latest = checkout / "workstation-reports" / "latest.json"
        latest.write_text(canonical)
        git(checkout, "add", "--", str(relative), "workstation-reports/latest.json")
        git(checkout, "commit", "-m",
            f"workstation-result: {report['run_id']} {report['status'].upper()}")
        commit = git(checkout, "rev-parse", "HEAD").stdout.strip()
        try:
            git(checkout, "push", "origin", branch)
        except ReportingError as exc:
            raise ReportingError(
                f"report committed locally as {commit} but push failed; retry publication") from exc
        return commit


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
