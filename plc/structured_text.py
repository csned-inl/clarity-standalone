"""Experimental analytic-policy to IEC 61131-3 Structured Text backend.

This module intentionally targets only CLARITY's serialized analytic predicate
policy. It is an experiment boundary, not a general SysML or IEC 61131-3
compiler.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping


GENERATOR_ID = "clarity.experimental-st.e001.v1"
POLICY_KIND = "sysml_derived_affine_predicate_policy"
INTEGER_TYPES = frozenset({"SINT", "INT", "DINT", "LINT"})
BASE_TYPE_MAP = {"Boolean": "BOOL", "Real": "LREAL"}
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RESERVED = frozenset({
    "and", "array", "at", "bool", "by", "case", "constant", "do",
    "dint", "else", "elsif", "end_case", "end_for", "end_function",
    "end_function_block", "end_if", "end_program", "end_repeat",
    "end_struct", "end_type", "end_var", "end_while", "exit", "false",
    "for", "function", "function_block", "if", "in", "int", "lint",
    "lreal", "mod", "not", "of", "or", "program", "real", "repeat",
    "return", "sint", "struct", "then", "to", "true", "type", "until",
    "var", "var_input", "var_output", "while", "xor",
})


class PLCGenerationError(ValueError):
    """The source artifacts cannot be translated without ambiguity."""


@dataclass(frozen=True)
class InterfaceVariable:
    name: str
    sysml_type: str
    st_type: str


@dataclass(frozen=True)
class StructuredTextArtifact:
    text: str
    manifest: dict[str, Any]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _load_policy(policy: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(policy, (str, Path)):
        value = json.loads(Path(policy).read_text())
    else:
        value = dict(policy)
    if not isinstance(value, dict):
        raise PLCGenerationError("policy must be a JSON object")
    if value.get("kind") != POLICY_KIND:
        raise PLCGenerationError(f"unsupported policy kind: {value.get('kind')!r}")
    return value


def _validate_identifier(name: str, *, role: str) -> None:
    if not IDENTIFIER.fullmatch(name) or name.lower() in RESERVED:
        raise PLCGenerationError(f"{role} is not a portable ST identifier: {name!r}")


def _type_map(sysml_type: str, integer_type: str | None) -> str:
    if sysml_type in BASE_TYPE_MAP:
        return BASE_TYPE_MAP[sysml_type]
    if sysml_type == "Integer":
        if integer_type is None:
            raise PLCGenerationError(
                "SysML Integer is unbounded; select an experimental PLC integer type")
        normalized = integer_type.upper()
        if normalized not in INTEGER_TYPES:
            raise PLCGenerationError(
                f"unsupported PLC integer type: {integer_type!r}")
        return normalized
    raise PLCGenerationError(f"unsupported SysML policy type: {sysml_type!r}")


def _interface(model_path: Path, integer_type: str | None):
    # Imports remain local so the PLC module can be inspected without mutating
    # the repository's historical sys.path behavior.
    import sys

    model_dir = str(Path(__file__).resolve().parents[1] / "sysml-models")
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)
    from sysml_parser import SysMLParser

    parser = SysMLParser(str(model_path))
    parser.parse()
    if not parser.controller_part:
        raise PLCGenerationError("model has no identified controller")
    controller_instance = parser.part_instances[parser.controller_part]
    controller = parser.part_defs[controller_instance.part_type]
    neural = [item for item in controller.action_defs if "Neural" in item.metadata]
    if len(neural) != 1:
        raise PLCGenerationError(
            f"expected exactly one #Neural action, found {len(neural)}")
    action = neural[0]
    inputs = [InterfaceVariable(p.name, p.type_name,
                                _type_map(p.type_name, integer_type))
              for p in action.in_params]
    outputs = [InterfaceVariable(p.name, p.type_name,
                                 _type_map(p.type_name, integer_type))
               for p in action.out_params]
    return action.name, inputs, outputs


def _output_references(node: Any, *, path: str = "rule") -> set[str]:
    if not isinstance(node, dict):
        raise PLCGenerationError(f"{path} must be an object")
    kind = node.get("kind")
    if kind == "output":
        name = node.get("name")
        if not isinstance(name, str):
            raise PLCGenerationError(f"{path}.name must be a string")
        return {name}
    if kind in {"literal", "affine_comparison"}:
        return set()
    if kind == "not":
        return _output_references(node.get("child"), path=f"{path}.child")
    if kind in {"and", "or"}:
        return (_output_references(node.get("left"), path=f"{path}.left") |
                _output_references(node.get("right"), path=f"{path}.right"))
    raise PLCGenerationError(f"unsupported predicate kind at {path}: {kind!r}")


def _rule_order(output_names: list[str], rules: Mapping[str, Any]) -> list[str]:
    output_set = set(output_names)
    dependencies: dict[str, set[str]] = {}
    for name in output_names:
        if name not in rules:
            raise PLCGenerationError(f"missing rule for output: {name}")
        refs = _output_references(rules[name], path=f"rules.{name}")
        unknown = refs - output_set
        if unknown:
            raise PLCGenerationError(
                f"rule {name} references unknown outputs: {sorted(unknown)}")
        dependencies[name] = refs
    extra = set(rules) - output_set
    if extra:
        raise PLCGenerationError(f"rules exist for unknown outputs: {sorted(extra)}")

    ordered: list[str] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            raise PLCGenerationError(f"cyclic output dependency involving {name}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in output_names:
            if dependency in dependencies[name]:
                visit(dependency)
        visiting.remove(name)
        visited.add(name)
        ordered.append(name)

    for name in output_names:
        visit(name)
    return ordered


def _numeric_value(value: Any, *, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PLCGenerationError(f"{path} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise PLCGenerationError(f"{path} must be finite")
    return result


def _real_number(value: Any, *, path: str) -> str:
    result = _numeric_value(value, path=path)
    text = repr(result)
    return "0.0" if text == "-0.0" else text


def _integer_number(value: Any, *, path: str) -> str:
    result = _numeric_value(value, path=path)
    if not result.is_integer():
        raise PLCGenerationError(
            f"{path} is not integral in an integer-domain affine expression")
    return str(int(result))


def _expression(node: Any, *, inputs: Mapping[str, str],
                outputs: set[str], path: str) -> str:
    if not isinstance(node, dict):
        raise PLCGenerationError(f"{path} must be an object")
    kind = node.get("kind")
    if kind == "literal":
        value = node.get("value")
        if type(value) is not bool:
            raise PLCGenerationError(f"{path}.value must be Boolean")
        return "TRUE" if value else "FALSE"
    if kind == "output":
        name = node.get("name")
        if name not in outputs:
            raise PLCGenerationError(f"{path} references unknown output: {name!r}")
        return name
    if kind == "not":
        child = _expression(node.get("child"), inputs=inputs, outputs=outputs,
                            path=f"{path}.child")
        return f"(NOT {child})"
    if kind in {"and", "or"}:
        left = _expression(node.get("left"), inputs=inputs, outputs=outputs,
                           path=f"{path}.left")
        right = _expression(node.get("right"), inputs=inputs, outputs=outputs,
                            path=f"{path}.right")
        return f"({left} {kind.upper()} {right})"
    if kind == "affine_comparison":
        operator = node.get("operator")
        if operator not in {"<", "<=", ">", ">="}:
            raise PLCGenerationError(f"unsupported comparison at {path}: {operator!r}")
        weights = node.get("weights")
        if not isinstance(weights, dict):
            raise PLCGenerationError(f"{path}.weights must be an object")
        unknown = set(weights) - set(inputs)
        if unknown:
            raise PLCGenerationError(
                f"{path} references unknown inputs: {sorted(unknown)}")
        referenced_types = {inputs[name] for name in weights}
        if "BOOL" in referenced_types:
            raise PLCGenerationError(f"{path} uses a Boolean in affine arithmetic")
        integer_domain = bool(referenced_types) and referenced_types <= INTEGER_TYPES
        if referenced_types & INTEGER_TYPES and not integer_domain:
            raise PLCGenerationError(
                f"{path} mixes integer and real inputs; no conversion policy is selected")
        number = _integer_number if integer_domain else _real_number
        terms = [number(node.get("bias"), path=f"{path}.bias")]
        for name in sorted(weights):
            terms.append(
                f"({number(weights[name], path=f'{path}.weights.{name}')} * {name})")
        zero = "0" if integer_domain else "0.0"
        return f"(({' + '.join(terms)}) {operator} {zero})"
    raise PLCGenerationError(f"unsupported predicate kind at {path}: {kind!r}")


def generate_structured_text(
    model_path: str | Path,
    policy: Mapping[str, Any] | str | Path,
    *,
    function_block_name: str,
    integer_type: str | None = None,
) -> StructuredTextArtifact:
    """Validate source artifacts and emit deterministic generic ST."""
    model_path = Path(model_path).resolve()
    policy_value = _load_policy(policy)
    _validate_identifier(function_block_name, role="function block name")

    model_hash = _sha256_bytes(model_path.read_bytes())
    if policy_value.get("source_model_sha256") != model_hash:
        raise PLCGenerationError("policy source-model hash does not match model")

    _action_name, inputs, outputs = _interface(model_path, integer_type)
    for variable in [*inputs, *outputs]:
        _validate_identifier(variable.name, role="interface name")
    lowered = [v.name.lower() for v in [*inputs, *outputs]]
    if len(lowered) != len(set(lowered)):
        raise PLCGenerationError("ST interface names collide case-insensitively")

    input_names = [v.name for v in inputs]
    output_names = [v.name for v in outputs]
    if policy_value.get("input_names") != sorted(input_names):
        raise PLCGenerationError("policy inputs do not exactly match #Neural inputs")
    if policy_value.get("output_names") != output_names:
        raise PLCGenerationError("policy outputs do not exactly match #Neural outputs")
    rules = policy_value.get("rules")
    if not isinstance(rules, dict):
        raise PLCGenerationError("policy rules must be an object")
    order = _rule_order(output_names, rules)

    input_types = {variable.name: variable.st_type for variable in inputs}
    output_set = set(output_names)
    lines = [
        "(* EXPERIMENTAL CLARITY E001 OUTPUT - not vendor-validated. *)",
        f"(* Source model SHA-256: {model_hash} *)",
        f"FUNCTION_BLOCK {function_block_name}",
        "VAR_INPUT",
    ]
    lines.extend(f"    {v.name} : {v.st_type};" for v in inputs)
    lines.extend(["END_VAR", "VAR_OUTPUT"])
    lines.extend(f"    {v.name} : {v.st_type};" for v in outputs)
    lines.extend(["END_VAR", ""])
    for name in order:
        expression = _expression(rules[name], inputs=input_types, outputs=output_set,
                                 path=f"rules.{name}")
        lines.append(f"{name} := {expression};")
    lines.extend(["END_FUNCTION_BLOCK", ""])
    text = "\n".join(lines)

    policy_hash = _sha256_bytes(_canonical_json(policy_value))
    type_mapping = {v.name: {"sysml": v.sysml_type, "st": v.st_type}
                    for v in [*inputs, *outputs]}
    manifest = {
        "schema_version": 1,
        "experiment": "E001",
        "generator": GENERATOR_ID,
        "target": "generic IEC 61131-3 Structured Text",
        "function_block": function_block_name,
        "source_model": policy_value.get("source_model"),
        "source_model_sha256": model_hash,
        "policy_kind": POLICY_KIND,
        "policy_canonical_sha256": policy_hash,
        "structured_text_sha256": _sha256_bytes(text.encode()),
        "inputs": input_names,
        "outputs": output_names,
        "assignment_order": order,
        "type_mapping": type_mapping,
        "assumptions": [
            "the function block is invoked once per intended controller decision",
            "the caller maps PLC variables and physical I/O to this interface",
            "LREAL arithmetic and comparison behavior is acceptable for this experiment",
            "selected bounded integer types do not overflow for intended inputs",
        ],
        "non_claims": [
            "no vendor dialect or PLC compiler has been validated",
            "no compiled-code semantic equivalence has been established",
            "no PLC scan, initialization, I/O, or fault semantics are supplied",
            "this artifact is not a safety certification",
        ],
    }
    return StructuredTextArtifact(text=text, manifest=manifest)


def write_structured_text_artifact(
    artifact: StructuredTextArtifact,
    output: str | Path,
    manifest: str | Path,
    *,
    overwrite: bool = False,
) -> None:
    output, manifest = Path(output), Path(manifest)
    if output.resolve() == manifest.resolve():
        raise PLCGenerationError("ST and manifest paths must differ")
    existing = [str(path) for path in (output, manifest) if path.exists()]
    if existing and not overwrite:
        raise PLCGenerationError(f"refusing to overwrite existing artifacts: {existing}")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(artifact.text)
    manifest.write_text(json.dumps(artifact.manifest, indent=2, sort_keys=True) + "\n")
