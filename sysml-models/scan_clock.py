"""Certified floating clock comparisons for source scan guards.

Model values remain native numbers. Fractions are helper bookkeeping for the
decimal values used by the parser/SMV emitter, never replacement model state.
"""
from dataclasses import dataclass
from fractions import Fraction
import math
import sys

from sysml_parser import AssignStmt, IfStmt, BinaryExpr, RefExpr, LiteralExpr, UnaryExpr


def decimal_value(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('scan clock requires finite numeric values')
    return Fraction(str(value))


def rounding_bound(value):
    """Half an ulp bounds round-to-nearest addition/subtraction, including zero."""
    if not math.isfinite(value):
        raise ValueError('scan clock overflow')
    return Fraction.from_float(math.ulp(float(value))) / 2


def exact_expression(expr, resolve):
    if isinstance(expr, LiteralExpr):
        return decimal_value(expr.value)
    if isinstance(expr, RefExpr):
        return decimal_value(resolve(expr))
    if isinstance(expr, UnaryExpr) and expr.op == '-':
        return -exact_expression(expr.operand, resolve)
    if isinstance(expr, BinaryExpr) and expr.op in ('+', '-', '*', '/'):
        left = exact_expression(expr.left, resolve)
        right = exact_expression(expr.right, resolve)
        return {'+': lambda: left + right, '-': lambda: left - right,
                '*': lambda: left * right, '/': lambda: left / right}[expr.op]()
    raise ValueError('unsupported scan period expression')


@dataclass(frozen=True)
class ScanGuard:
    increment: AssignStmt
    guard: IfStmt
    snapshot: AssignStmt
    current: RefExpr
    previous: RefExpr


def scan_guards(stmts):
    """Recognize the source sequence clock += dt; if elapsed >= period: last=clock.

    Restrict recognition to adjacent statements with the snapshot first in the
    body, so the comparison and assignment order is unambiguous.
    """
    for increment, guard in zip(stmts, stmts[1:]):
        if not isinstance(increment, AssignStmt) or not isinstance(guard, IfStmt):
            continue
        inc, cond = increment.expr, guard.condition
        if not (isinstance(inc, BinaryExpr) and inc.op == '+' and
                isinstance(inc.left, RefExpr) and inc.left.path == increment.target and
                isinstance(inc.right, RefExpr) and inc.right.path == ['dt'] and
                isinstance(cond, BinaryExpr) and cond.op == '>=' and
                isinstance(cond.left, BinaryExpr) and cond.left.op == '-' and
                isinstance(cond.left.left, RefExpr) and
                cond.left.left.path == increment.target and
                isinstance(cond.left.right, RefExpr) and guard.body):
            continue
        snapshot = guard.body[0]
        if (isinstance(snapshot, AssignStmt) and
                snapshot.target == cond.left.right.path and
                isinstance(snapshot.expr, RefExpr) and snapshot.expr.path == increment.target):
            yield ScanGuard(increment, guard, snapshot, cond.left.left, cond.left.right)


def after_increment(expr, spec):
    """Substitute only this scan's prior clock update for SMV simultaneous next()."""
    if isinstance(expr, RefExpr) and expr.path == spec.current.path:
        return spec.increment.expr
    if isinstance(expr, BinaryExpr):
        return BinaryExpr(expr.op, after_increment(expr.left, spec),
                          after_increment(expr.right, spec))
    if isinstance(expr, UnaryExpr):
        return UnaryExpr(expr.op, after_increment(expr.operand, spec))
    return expr


class ScanClock:
    def __init__(self, current=0.0, previous=0.0):
        if sys.float_info.radix != 2 or sys.float_info.mant_dig != 53 or sys.float_info.rounds != 1:
            raise ValueError('scan error analysis requires round-to-nearest binary64')
        self.current = current
        self.previous = previous
        self.exact_current = decimal_value(current)
        self.exact_previous = decimal_value(previous)
        self.current_error = abs(Fraction(current) - self.exact_current)
        self.previous_error = abs(Fraction(previous) - self.exact_previous)
        self.updates = self.comparisons = self.fallbacks = self.corrections = 0
        self.max_bound = Fraction(0)
        self.last_bound = Fraction(0)

    def advance(self, before, dt, after):
        if before != self.current or after != before + dt:
            raise ValueError('scan clock history changed outside its source increment')
        exact_dt = decimal_value(dt)
        if exact_dt <= 0:
            raise ValueError('scan timestep must be positive')
        # Triangle inequality: prior clock error + dt representation error +
        # correctly rounded addition error. No assumed episode/tick bound.
        self.current_error += abs(Fraction(dt) - exact_dt) + rounding_bound(after)
        self.exact_current += exact_dt
        self.current = after
        self.updates += 1

    def due(self, current, previous, period, numeric_period):
        if current != self.current or previous != self.previous:
            raise ValueError('scan clock history changed outside source assignments')
        if period <= 0:
            raise ValueError('scan period must be positive')
        if not math.isfinite(numeric_period):
            raise ValueError('scan period must be finite')
        elapsed = current - previous
        bound = self.current_error + self.previous_error + rounding_bound(elapsed)
        self.last_bound = bound
        self.max_bound = max(self.max_bound, bound)
        self.comparisons += 1
        # Outward rounding prevents the threshold calculation itself from
        # introducing an early/late decision. A fixed epsilon is not used.
        low = math.nextafter(float(period - bound), -math.inf)
        high = math.nextafter(float(period + bound), math.inf)
        if elapsed < low:
            result = False
        elif elapsed > high:
            result = True
        else:
            self.fallbacks += 1
            result = self.exact_current - self.exact_previous >= period
        self.corrections += result != (elapsed >= numeric_period)
        return result

    def snapshot(self, value):
        if value != self.current:
            raise ValueError('scan snapshot must copy current source clock')
        self.previous = value
        self.exact_previous = self.exact_current
        self.previous_error = self.current_error

    def report(self):
        upper = math.nextafter(float(self.max_bound), math.inf)
        return {'clock_updates': self.updates, 'comparisons': self.comparisons,
                'exact_fallbacks': self.fallbacks, 'corrected_comparisons': self.corrections,
                'maximum_error_bound_seconds': upper}
