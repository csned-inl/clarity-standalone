"""Source-owned execution parameters shared by every CLARITY pipeline stage.

The SysML source is authoritative.  Values tagged ``#ExecutionParameter`` are
loaded once, typed, fingerprinted, and then propagated to simulators, proof
extractors, trainers, and result metadata.  Callers may validate an explicitly
supplied value, but they may not silently replace the source value.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


_DECLARATION = re.compile(
    r"#ExecutionParameter\s+attribute\s+"
    r"(?P<name>[A-Za-z_]\w*)\s*:\s*"
    r"(?P<type>Real|Integer|Boolean)\s*=\s*"
    r"(?P<value>true|false|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*;"
)


def _without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"//[^\r\n]*", "", source)


def _typed_value(type_name: str, text: str):
    if type_name == "Boolean":
        return text == "true"
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid {type_name} execution parameter: {text}") from exc
    if not value.is_finite():
        raise ValueError(f"execution parameter must be finite: {text}")
    if type_name == "Integer":
        if value != value.to_integral_value():
            raise ValueError(f"Integer execution parameter is not integral: {text}")
        return int(value)
    return value


@dataclass(frozen=True)
class ExecutionParameters:
    """Immutable, source-derived execution configuration."""

    model: str
    values: Mapping[str, object]
    fingerprint: str

    def require_decimal(self, name: str) -> Decimal:
        value = self.values.get(name)
        if not isinstance(value, Decimal):
            raise ValueError(f"missing or non-Real execution parameter: {name}")
        return value

    def require_integer(self, name: str) -> int:
        value = self.values.get(name)
        if type(value) is not int:
            raise ValueError(f"missing or non-Integer execution parameter: {name}")
        return value

    def require_boolean(self, name: str) -> bool:
        value = self.values.get(name)
        if type(value) is not bool:
            raise ValueError(f"missing or non-Boolean execution parameter: {name}")
        return value

    @property
    def controller_interval_seconds(self) -> Decimal:
        value = self.require_decimal("controllerIntervalSeconds")
        if value <= 0:
            raise ValueError("controllerIntervalSeconds must be positive")
        return value

    @property
    def integration_substeps(self) -> int:
        value = self.require_integer(
            "integrationSubstepsPerControllerInterval")
        if value <= 0:
            raise ValueError(
                "integrationSubstepsPerControllerInterval must be positive")
        return value

    @property
    def integration_step_seconds(self) -> Decimal:
        return self.controller_interval_seconds / self.integration_substeps

    @property
    def integration_step_float(self) -> float:
        value = float(self.integration_step_seconds)
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError("derived integration step must be finite and positive")
        return value

    def require_matching_integration_step(self, supplied: float) -> float:
        if not math.isfinite(supplied) or supplied <= 0.0:
            raise ValueError("integration step must be finite and positive")
        expected = self.integration_step_float
        if not math.isclose(supplied, expected, rel_tol=1e-12, abs_tol=0.0):
            raise ValueError(
                "integration step disagrees with SysML execution parameters: "
                f"supplied={supplied:.17g}, expected={expected:.17g}")
        return expected

    def as_dict(self) -> dict:
        source_values = {
            name: (format(value, "f") if isinstance(value, Decimal) else value)
            for name, value in sorted(self.values.items())
        }
        return {
            "source": self.model,
            "source_values": source_values,
            "controller_interval_seconds": float(
                self.controller_interval_seconds),
            "integration_substeps_per_controller_interval": (
                self.integration_substeps),
            "integration_step_seconds": self.integration_step_float,
            "fingerprint": self.fingerprint,
        }


def load_execution_parameters(model_path: str | Path) -> ExecutionParameters:
    """Load every ``#ExecutionParameter`` literal from one SysML model."""
    model = Path(model_path).resolve()
    source = _without_comments(model.read_text())
    values: dict[str, object] = {}
    serialized: list[dict[str, object]] = []
    for match in _DECLARATION.finditer(source):
        name = match.group("name")
        if name in values:
            raise ValueError(f"duplicate #ExecutionParameter: {name}")
        type_name = match.group("type")
        text = match.group("value")
        value = _typed_value(type_name, text)
        values[name] = value
        serialized.append({"name": name, "type": type_name, "value": text})
    if not values:
        raise ValueError(f"model has no #ExecutionParameter declarations: {model}")
    canonical = json.dumps(
        sorted(serialized, key=lambda row: row["name"]),
        sort_keys=True, separators=(",", ":"),
    ).encode()
    parameters = ExecutionParameters(
        model=str(model),
        values=MappingProxyType(values),
        fingerprint=hashlib.sha256(canonical).hexdigest(),
    )
    # Force validation of the common timing contract at load time.
    parameters.integration_step_float
    return parameters


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print the source-owned execution configuration as JSON")
    parser.add_argument("model", type=Path)
    parser.add_argument(
        "--expect-fingerprint",
        help="fail unless the source values have this exact fingerprint")
    args = parser.parse_args()
    execution = load_execution_parameters(args.model)
    if (args.expect_fingerprint is not None
            and args.expect_fingerprint != execution.fingerprint):
        parser.error(
            "execution-parameter fingerprint mismatch: "
            f"expected {args.expect_fingerprint}, found {execution.fingerprint}")
    print(json.dumps(execution.as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
