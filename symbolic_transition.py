"""Exact affine symbolic transitions compiled from generated SMV.

The importer is intentionally fail-closed.  It accepts only arithmetic needed
by the deterministic real-valued scan-cycle fast path; unsupported syntax or
ambiguous case selection raises instead of approximating the model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
import hashlib
import re
from typing import Callable, Iterable


Q = Fraction


@dataclass(frozen=True)
class AffineForm:
    constant: Q = Q(0)
    terms: tuple[tuple[str, Q], ...] = ()

    @staticmethod
    def value(value: Q | int | str) -> "AffineForm":
        return AffineForm(Q(value), ())

    @staticmethod
    def variable(name: str) -> "AffineForm":
        return AffineForm(Q(0), ((name, Q(1)),))

    @staticmethod
    def build(constant: Q, terms: dict[str, Q]) -> "AffineForm":
        return AffineForm(
            constant,
            tuple(sorted((name, coefficient) for name, coefficient in terms.items()
                         if coefficient)),
        )

    def coefficients(self) -> dict[str, Q]:
        return dict(self.terms)

    def __add__(self, other: "AffineForm") -> "AffineForm":
        terms = self.coefficients()
        for name, coefficient in other.terms:
            terms[name] = terms.get(name, Q(0)) + coefficient
        return AffineForm.build(self.constant + other.constant, terms)

    def __neg__(self) -> "AffineForm":
        return AffineForm.build(
            -self.constant, {name: -value for name, value in self.terms})

    def __sub__(self, other: "AffineForm") -> "AffineForm":
        return self + (-other)

    def scale(self, scalar: Q) -> "AffineForm":
        return AffineForm.build(
            self.constant * scalar,
            {name: value * scalar for name, value in self.terms},
        )

    def __mul__(self, other: "AffineForm") -> "AffineForm":
        if not self.terms:
            return other.scale(self.constant)
        if not other.terms:
            return self.scale(other.constant)
        raise ValueError("nonlinear multiplication is not affine")

    def __truediv__(self, other: "AffineForm") -> "AffineForm":
        if other.terms or other.constant == 0:
            raise ValueError("division requires a nonzero constant denominator")
        return self.scale(Q(1, 1) / other.constant)

    def substitute(self, replacements: dict[str, "AffineForm"]) -> "AffineForm":
        result = AffineForm.value(self.constant)
        for name, coefficient in self.terms:
            result += replacements.get(name, AffineForm.variable(name)).scale(coefficient)
        return result


class _AffineParser:
    TOKEN = re.compile(
        r"\s*(?:(?P<number>\d+(?:\.\d+)?)|(?P<name>[A-Za-z_]\w*)|"
        r"(?P<op>[()+\-*/]))")

    def __init__(self, source: str, resolve: Callable[[str], AffineForm]):
        self.resolve = resolve
        self.tokens: list[tuple[str, str]] = []
        position = 0
        while position < len(source):
            match = self.TOKEN.match(source, position)
            if not match:
                raise ValueError(f"unsupported affine syntax near {source[position:]!r}")
            kind = "number" if match.group("number") else (
                "name" if match.group("name") else "op")
            self.tokens.append((kind, match.group(kind)))
            position = match.end()
        self.index = 0

    def parse(self) -> AffineForm:
        result = self._additive()
        if self.index != len(self.tokens):
            raise ValueError(f"unexpected token {self.tokens[self.index]}")
        return result

    def _peek(self, value: str) -> bool:
        return self.index < len(self.tokens) and self.tokens[self.index][1] == value

    def _take(self) -> tuple[str, str]:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def _additive(self) -> AffineForm:
        result = self._multiplicative()
        while self._peek("+") or self._peek("-"):
            operator = self._take()[1]
            right = self._multiplicative()
            result = result + right if operator == "+" else result - right
        return result

    def _multiplicative(self) -> AffineForm:
        result = self._unary()
        while self._peek("*") or self._peek("/"):
            operator = self._take()[1]
            right = self._unary()
            result = result * right if operator == "*" else result / right
        return result

    def _unary(self) -> AffineForm:
        if self._peek("+"):
            self._take()
            return self._unary()
        if self._peek("-"):
            self._take()
            return -self._unary()
        return self._primary()

    def _primary(self) -> AffineForm:
        if self._peek("("):
            self._take()
            result = self._additive()
            if not self._peek(")"):
                raise ValueError("missing closing parenthesis")
            self._take()
            return result
        kind, value = self._take()
        if kind == "number":
            return AffineForm.value(value)
        if kind == "name":
            return self.resolve(value)
        raise ValueError(f"unexpected token {(kind, value)}")


@dataclass(frozen=True)
class CaseBranch:
    condition: str
    expression: str


@dataclass(frozen=True)
class UnsaturatedActuator:
    executed_state: str
    proposal_symbol: str
    availability_symbol: str
    limit_symbol: str


@dataclass(frozen=True)
class AffineTransitionSystem:
    states: tuple[str, ...]
    parameters: tuple[str, ...]
    next_state: dict[str, AffineForm]
    initial_state: dict[str, Q]
    parameter_bounds: dict[str, tuple[Q, Q]]
    source_sha256: str
    mode_assumptions: tuple[str, ...] = ()
    metadata: dict[str, str] = field(default_factory=dict)

    def dependency_slice(self, outputs: Iterable[str]) -> "AffineTransitionSystem":
        needed = set(outputs)
        unknown = needed - set(self.states)
        if unknown:
            raise ValueError(f"slice outputs are not states: {sorted(unknown)}")
        changed = True
        while changed:
            changed = False
            for state in tuple(needed):
                for name, _coefficient in self.next_state[state].terms:
                    if name in self.states and name not in needed:
                        needed.add(name)
                        changed = True
        states = tuple(name for name in self.states if name in needed)
        parameters = tuple(
            name for name in self.parameters
            if any(name in dict(self.next_state[state].terms) for state in states)
        )
        return AffineTransitionSystem(
            states=states,
            parameters=parameters,
            next_state={name: self.next_state[name] for name in states},
            initial_state={name: self.initial_state[name] for name in states},
            parameter_bounds={name: self.parameter_bounds[name] for name in parameters},
            source_sha256=self.source_sha256,
            mode_assumptions=self.mode_assumptions,
            metadata=dict(self.metadata),
        )

    def matrices(self) -> tuple[list[list[Q]], list[list[Q]], list[Q]]:
        state_index = {name: index for index, name in enumerate(self.states)}
        parameter_index = {name: index for index, name in enumerate(self.parameters)}
        a = [[Q(0) for _ in self.states] for _ in self.states]
        b = [[Q(0) for _ in self.parameters] for _ in self.states]
        c = [Q(0) for _ in self.states]
        for row, state in enumerate(self.states):
            form = self.next_state[state]
            c[row] = form.constant
            for name, coefficient in form.terms:
                if name in state_index:
                    a[row][state_index[name]] += coefficient
                elif name in parameter_index:
                    b[row][parameter_index[name]] += coefficient
                else:
                    raise ValueError(f"unclassified affine symbol {name!r}")
        return a, b, c


def _section(source: str, start: str, stops: tuple[str, ...]) -> list[str]:
    lines = source.splitlines()
    try:
        first = next(i for i, line in enumerate(lines) if line.strip() == start) + 1
    except StopIteration:
        return []
    result = []
    for line in lines[first:]:
        if line.strip() in stops:
            break
        result.append(line)
    return result


def _declarations(source: str, section: str) -> list[str]:
    stops = ("VAR", "FROZENVAR", "IVAR", "DEFINE", "INIT", "TRANS", "ASSIGN")
    result = []
    for line in _section(source, section, stops):
        match = re.match(r"\s*([A-Za-z_]\w*)\s*:\s*real\s*;", line)
        if match:
            result.append(match.group(1))
    return result


def _definitions(source: str) -> dict[str, str]:
    result = {}
    for line in _section(source, "DEFINE", ("INIT", "TRANS", "ASSIGN")):
        match = re.match(r"\s*([A-Za-z_]\w*)\s*:=\s*(.*?)\s*;\s*$", line)
        if match:
            result[match.group(1)] = match.group(2)
    # A deterministic TRANS equality constrains the neural IVAR and is an
    # arithmetic alias for this fast path.
    for line in _section(source, "TRANS", ("ASSIGN",)):
        match = re.match(r"\s*([A-Za-z_]\w*)\s*=\s*(.*?)\s*;\s*$", line)
        if match:
            result[match.group(1)] = match.group(2)
    return result


def _assignments(source: str) -> tuple[dict[str, str], dict[str, list[CaseBranch]]]:
    lines = _section(source, "ASSIGN", ("-- Verification properties",))
    initial: dict[str, str] = {}
    following: dict[str, list[CaseBranch]] = {}
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        init_match = re.match(r"init\((\w+)\)\s*:=\s*(.*?)\s*;\s*$", stripped)
        if init_match:
            initial[init_match.group(1)] = init_match.group(2)
            index += 1
            continue
        simple = re.match(r"next\((\w+)\)\s*:=\s*(.*?)\s*;\s*$", stripped)
        if simple:
            following[simple.group(1)] = [CaseBranch("TRUE", simple.group(2))]
            index += 1
            continue
        block = re.match(r"next\((\w+)\)\s*:=\s*$", stripped)
        if not block:
            index += 1
            continue
        name = block.group(1)
        index += 1
        if index >= len(lines) or lines[index].strip() != "case":
            raise ValueError(f"next({name}) is not a supported case assignment")
        index += 1
        branches = []
        while index < len(lines) and lines[index].strip() != "esac;":
            branch = re.match(r"\s*(.*?)\s*:\s*(.*?)\s*;\s*$", lines[index])
            if not branch:
                raise ValueError(f"unsupported case branch: {lines[index]!r}")
            branches.append(CaseBranch(branch.group(1), branch.group(2)))
            index += 1
        if index >= len(lines):
            raise ValueError(f"unterminated case for next({name})")
        following[name] = branches
        index += 1
    return initial, following


def _choose_phase_branch(
    name: str,
    branches: list[CaseBranch],
    phase: int,
    actuator: UnsaturatedActuator,
) -> str:
    if name == "scan_phase":
        raise ValueError("scan_phase is not an affine physical state")
    if name == actuator.executed_state:
        if phase == 0:
            return branches[-1].expression
        candidates = [
            branch for branch in branches
            if actuator.availability_symbol in branch.condition
            and "<=" in branch.condition and ">=" in branch.condition
        ]
        if len(candidates) != 1:
            raise ValueError("could not identify the unique unsaturated actuator branch")
        return candidates[0].expression
    if branches and "scan_phase != 0" in branches[0].condition:
        if phase != 0:
            return branches[0].expression
        for branch in branches[1:]:
            if branch.condition == "TRUE":
                return branch.expression
        raise ValueError(f"no phase-zero update for {name}")
    # Other actuator-owned state is irrelevant to the envelope slice.  Keep
    # it held at phase zero and choose its interior branch at phase one.
    if any(actuator.availability_symbol in branch.condition for branch in branches):
        if phase == 0:
            return branches[-1].expression
        candidates = [branch for branch in branches if branch.condition != "TRUE"]
        if not candidates:
            raise ValueError(f"no actuator branch for {name}")
        return candidates[-1].expression
    if len(branches) == 1 and branches[0].condition == "TRUE":
        return branches[0].expression
    raise ValueError(f"unsupported phase selection for {name}")


def compile_unsaturated_scan_cycle(
    source: str,
    *,
    actuator: UnsaturatedActuator,
    parameter_bounds: dict[str, tuple[Q, Q]] | None = None,
) -> AffineTransitionSystem:
    """Compile two emitted scan phases into one exact affine recurrence."""
    states = tuple(_declarations(source, "VAR"))
    parameters = tuple(_declarations(source, "FROZENVAR"))
    if parameter_bounds is None:
        parameter_bounds = _extract_parameter_bounds(source, parameters)
    if set(parameter_bounds) != set(parameters):
        raise ValueError("parameter bounds must cover every FROZENVAR exactly")
    definitions = _definitions(source)
    initial_text, assignments = _assignments(source)
    missing = set(states) - set(assignments)
    if missing:
        raise ValueError(f"states without next assignments: {sorted(missing)}")

    resolving: set[str] = set()
    resolved: dict[str, AffineForm] = {}

    def resolve(name: str) -> AffineForm:
        if name in states or name in parameters:
            return AffineForm.variable(name)
        if name in resolved:
            return resolved[name]
        if name not in definitions:
            raise ValueError(f"undefined affine symbol {name!r}")
        if name in resolving:
            raise ValueError(f"cyclic DEFINE involving {name!r}")
        resolving.add(name)
        form = _AffineParser(definitions[name], resolve).parse()
        resolving.remove(name)
        resolved[name] = form
        return form

    def lower(text: str) -> AffineForm:
        return _AffineParser(text, resolve).parse()

    if definitions.get(actuator.availability_symbol, "").replace(" ", "") != "(scan_phase=1)":
        raise ValueError("actuator availability is not the expected phase-one event")
    limit = resolve(actuator.limit_symbol)
    if limit.terms or limit.constant <= 0:
        raise ValueError("actuator limit is not a positive constant")

    parameter_identity = {name: AffineForm.variable(name) for name in parameters}
    phase_zero = {
        name: lower(_choose_phase_branch(name, assignments[name], 0, actuator))
        for name in states
    }
    phase_zero.update(parameter_identity)
    phase_one_local = {
        name: lower(_choose_phase_branch(name, assignments[name], 1, actuator))
        for name in states
    }
    complete_cycle = {
        name: form.substitute(phase_zero)
        for name, form in phase_one_local.items()
    }

    initial: dict[str, Q] = {}
    for state in states:
        if state not in initial_text:
            raise ValueError(f"state {state!r} has no initial value")
        value = lower(initial_text[state])
        if value.terms:
            raise ValueError(f"initial state {state!r} is not constant")
        initial[state] = value.constant

    return AffineTransitionSystem(
        states=states,
        parameters=parameters,
        next_state=complete_cycle,
        initial_state=initial,
        parameter_bounds=parameter_bounds,
        source_sha256=hashlib.sha256(source.encode()).hexdigest(),
        mode_assumptions=(
            f"abs({actuator.proposal_symbol}) <= {limit.constant}",
        ),
        metadata={
            "compiled_phases": "0,1",
            "actuator_limit": str(limit.constant),
            "actuator_state": actuator.executed_state,
        },
    )


def _extract_parameter_bounds(
    source: str, parameters: tuple[str, ...]
) -> dict[str, tuple[Q, Q]]:
    init = " ".join(line.strip() for line in _section(
        source, "INIT", ("TRANS", "ASSIGN")))
    number = r"\(?\s*(-?\d+(?:\.\d+)?)\s*\)?"
    bounds: dict[str, tuple[Q, Q]] = {}
    for parameter in parameters:
        lower = re.search(rf"\b{re.escape(parameter)}\s*>=\s*{number}", init)
        upper = re.search(rf"\b{re.escape(parameter)}\s*<=\s*{number}", init)
        if not lower or not upper:
            raise ValueError(f"missing explicit bounds for FROZENVAR {parameter!r}")
        bounds[parameter] = (Q(lower.group(1)), Q(upper.group(1)))
    return bounds


def constant_definition(source: str, name: str) -> Q:
    """Return an exact constant DEFINE, rejecting state-dependent aliases."""
    definitions = _definitions(source)
    if name not in definitions:
        raise ValueError(f"missing DEFINE {name!r}")
    form = _AffineParser(
        definitions[name],
        lambda symbol: (_ for _ in ()).throw(
            ValueError(f"DEFINE {name!r} depends on {symbol!r}")),
    ).parse()
    if form.terms:
        raise ValueError(f"DEFINE {name!r} is not constant")
    return form.constant
