"""Exact finite-prefix plus contraction certificates for affine recurrences."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from time import monotonic

from symbolic_transition import AffineTransitionSystem


Q = Fraction


@dataclass(frozen=True)
class ScalarSafetyObjective:
    parameter: str
    safety_state: str
    safety_bound: Q
    mode_state: str
    mode_bound: Q
    prefix_steps: int
    block_steps: int


def _mv(matrix: list[list[Q]], vector: list[Q]) -> list[Q]:
    return [
        sum((coefficient * vector[j] for j, coefficient in enumerate(row)
             if coefficient), Q(0))
        for row in matrix
    ]


def _vm(vector: list[Q], matrix: list[list[Q]]) -> list[Q]:
    result = [Q(0) for _ in vector]
    for i, value in enumerate(vector):
        if not value:
            continue
        for j, coefficient in enumerate(matrix[i]):
            if coefficient:
                result[j] += value * coefficient
    return result


def _mm(left: list[list[Q]], right: list[list[Q]]) -> list[list[Q]]:
    size = len(left)
    result = [[Q(0) for _ in range(size)] for _ in range(size)]
    for i, row in enumerate(left):
        for k, value in enumerate(row):
            if not value:
                continue
            for j, coefficient in enumerate(right[k]):
                if coefficient:
                    result[i][j] += value * coefficient
    return result


def _power(matrix: list[list[Q]], exponent: int) -> list[list[Q]]:
    size = len(matrix)
    result = [[Q(i == j) for j in range(size)] for i in range(size)]
    factor = matrix
    while exponent:
        if exponent & 1:
            result = _mm(result, factor)
        exponent //= 2
        if exponent:
            factor = _mm(factor, factor)
    return result


def _solve(matrix: list[list[Q]], rhs: list[Q]) -> list[Q]:
    size = len(matrix)
    rows = [list(matrix[i]) + [rhs[i]] for i in range(size)]
    for column in range(size):
        pivot = next((row for row in range(column, size)
                      if rows[row][column]), None)
        if pivot is None:
            raise ValueError("affine equilibrium is not uniquely solvable")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for row in range(size):
            if row == column or not rows[row][column]:
                continue
            factor = rows[row][column]
            rows[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(rows[row], rows[column])
            ]
    return [rows[i][-1] for i in range(size)]


def _as_float(value: Q) -> float:
    return float(value)


def certify_scalar_affine_safety(
    system: AffineTransitionSystem,
    objective: ScalarSafetyObjective,
) -> dict[str, object]:
    """Prove one bounded output and the affine-mode guard for all time.

    This fast path is intentionally incomplete.  It accepts one symmetrically
    bounded frozen parameter, zero initial state, and a homogeneous affine
    recurrence after shifting to the parameter-dependent equilibrium.
    """
    started = monotonic()
    if system.parameters != (objective.parameter,):
        raise ValueError("certificate requires exactly the named scalar parameter")
    if objective.safety_state not in system.states:
        raise ValueError("safety state is absent from the transition slice")
    if objective.mode_state not in system.states:
        raise ValueError("mode-guard state is absent from the transition slice")
    lower, upper = system.parameter_bounds[objective.parameter]
    if lower != -upper or upper <= 0:
        raise ValueError("parameter interval must be symmetric about zero")
    if any(system.initial_state[state] != 0 for state in system.states):
        raise ValueError("certificate currently requires a zero initial state")

    a, b_matrix, constant = system.matrices()
    if any(constant):
        raise ValueError("certificate currently requires zero affine offset")
    b = [row[0] for row in b_matrix]
    size = len(system.states)
    identity_minus_a = [
        [Q(i == j) - a[i][j] for j in range(size)]
        for i in range(size)
    ]
    equilibrium = _solve(identity_minus_a, b)
    if [left + right for left, right in zip(_mv(a, equilibrium), b)] != equilibrium:
        raise AssertionError("computed equilibrium failed exact substitution")

    safety_index = system.states.index(objective.safety_state)
    mode_index = system.states.index(objective.mode_state)
    error = [-value for value in equilibrium]
    prefix_safety_gain = abs(equilibrium[safety_index] + error[safety_index])
    prefix_mode_gain = abs(equilibrium[mode_index] + error[mode_index])
    for _ in range(objective.prefix_steps):
        error = _mv(a, error)
        prefix_safety_gain = max(
            prefix_safety_gain,
            abs(equilibrium[safety_index] + error[safety_index]),
        )
        prefix_mode_gain = max(
            prefix_mode_gain,
            abs(equilibrium[mode_index] + error[mode_index]),
        )
    prefix_safety = prefix_safety_gain * upper
    prefix_mode = prefix_mode_gain * upper
    if not prefix_safety < objective.safety_bound:
        raise AssertionError("finite prefix violates the safety bound")
    if not prefix_mode < objective.mode_bound:
        raise AssertionError("finite prefix leaves the selected affine mode")

    checkpoint_error_gain = max(map(abs, error))
    safety_row = [Q(i == safety_index) for i in range(size)]
    mode_row = [Q(i == mode_index) for i in range(size)]
    safety_interblock_gain = Q(0)
    mode_interblock_gain = Q(0)
    for _ in range(objective.block_steps + 1):
        safety_interblock_gain = max(
            safety_interblock_gain, sum(map(abs, safety_row), Q(0)))
        mode_interblock_gain = max(
            mode_interblock_gain, sum(map(abs, mode_row), Q(0)))
        safety_row = _vm(safety_row, a)
        mode_row = _vm(mode_row, a)

    block_map = _power(a, objective.block_steps)
    contraction = max(sum(map(abs, row), Q(0)) for row in block_map)
    if not contraction < 1:
        raise AssertionError("block transition is not a strict contraction")

    tail_safety = (
        abs(equilibrium[safety_index])
        + checkpoint_error_gain * safety_interblock_gain
    ) * upper
    tail_mode = (
        abs(equilibrium[mode_index])
        + checkpoint_error_gain * mode_interblock_gain
    ) * upper
    if not tail_safety < objective.safety_bound:
        raise AssertionError("tail contraction does not imply the safety bound")
    if not tail_mode < objective.mode_bound:
        raise AssertionError("tail contraction does not preserve the affine mode")

    return {
        "schema": "clarity.affine-safety-certificate.v1",
        "source_sha256": system.source_sha256,
        "arithmetic": "exact-rational",
        "state_dimension": size,
        "parameter": objective.parameter,
        "prefix_steps": objective.prefix_steps,
        "block_steps": objective.block_steps,
        "contraction_upper_bound": _as_float(contraction),
        "prefix_max_abs_safety_state": _as_float(prefix_safety),
        "prefix_max_abs_mode_state": _as_float(prefix_mode),
        "tail_max_abs_safety_state": _as_float(tail_safety),
        "tail_max_abs_mode_state": _as_float(tail_mode),
        "required_safety_bound": _as_float(objective.safety_bound),
        "required_mode_bound": _as_float(objective.mode_bound),
        "mode_assumptions": list(system.mode_assumptions),
        "proved": True,
        "elapsed_seconds": monotonic() - started,
    }
