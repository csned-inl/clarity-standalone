"""Scan decisions and roundoff bounds checked against independent exact oracles."""
import importlib.util
import math
from fractions import Fraction
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'sysml-models'), str(ROOT / 'rl')]
from scan_clock import ScanClock, decimal_value, exact_expression, scan_guards
from sysml_parser import SysMLParser, ExpressionParser
from simulator import SimulationEngine

MODEL = ROOT / 'sysml-models/mixing-sysml-model/model.sysml'


def precision_audit():
    rows = []
    configurations = [(.1, Fraction(1, 10)), (.03, Fraction(1, 10)),
                      (.05, Fraction(1, 10)), (.2, Fraction(1, 10)),
                      (.1, Fraction(1, 7)), (.1, Fraction(1, 20)),
                      (.01, Fraction(1, 3)),
                      (.1, decimal_value(math.nextafter(.1, math.inf))),
                      (.1, decimal_value(math.nextafter(.1, -math.inf))),
                      (.1, Fraction('0.10000000000000000001')),
                      (.125, Fraction(1, 4)), (1e-12, Fraction('3e-12'))]
    for dt, period in configurations:
        clock = ScanClock()
        current = previous = 0.0
        exact_current = exact_previous = Fraction(0)
        smallest_margin = None
        for tick in range(1, 4097):
            after = current + dt
            clock.advance(current, dt, after)
            current = after
            exact_current = tick * Fraction(str(dt))
            # Independent subtraction of exact binary representations checks
            # the calculated bound, rather than repeating the bound formula.
            actual_error = abs(Fraction(current) - exact_current)
            assert actual_error <= clock.current_error
            elapsed = current - previous
            exact_elapsed = exact_current - exact_previous
            actual_elapsed_error = abs(Fraction(elapsed) - exact_elapsed)
            due = clock.due(current, previous, period, float(period))
            assert due == (exact_elapsed >= period)
            assert actual_elapsed_error <= clock.last_bound
            margin = clock.current_error - actual_error
            smallest_margin = margin if smallest_margin is None else min(smallest_margin, margin)
            if due:
                clock.snapshot(current)
                previous = current
                exact_previous = exact_current
        rows.append({'dt_seconds': dt, 'period_exact': str(period),
                     'ticks_checked': 4096, 'bound_and_decisions_match_exact_oracle': True,
                     **clock.report()})
    return rows


class ScanClockTests(unittest.TestCase):
    def test_precision_and_decisions_across_scan_intervals(self):
        self.assertEqual(len(precision_audit()), 12)

    def test_current_2402_update_bound(self):
        clock = ScanClock()
        current = previous = 0.0
        for _ in range(2402):
            after = current + .1
            clock.advance(current, .1, after)
            current = after
            self.assertTrue(clock.due(current, previous, Fraction(1, 10), .1))
            clock.snapshot(current)
            previous = current
        self.assertLess(float(clock.max_bound), 2e-10)
        self.assertGreater(clock.corrections, 0)

    def test_ambiguous_genuinely_later_period_does_not_fire_early(self):
        clock = ScanClock()
        clock.advance(0., .1, .1)
        period = Fraction('0.10000000000000000001')
        self.assertFalse(clock.due(.1, 0., period, .1))
        self.assertEqual(clock.fallbacks, 1)

    def test_variable_timestep_history(self):
        clock = ScanClock()
        now = last = 0.
        exact_now = exact_last = Fraction(0)
        for dt in [.03, .07, .05, .001, .049] * 500:
            after = now + dt
            clock.advance(now, dt, after)
            now = after
            exact_now += Fraction(str(dt))
            due = clock.due(now, last, Fraction(1, 10), .1)
            self.assertEqual(due, exact_now - exact_last >= Fraction(1, 10))
            if due:
                clock.snapshot(now)
                last, exact_last = now, exact_now

    def test_history_change_and_bad_values_fail(self):
        clock = ScanClock()
        with self.assertRaises(ValueError): clock.advance(1., .1, 1.1)
        with self.assertRaises(ValueError): clock.advance(0., 0., 0.)
        with self.assertRaises(ValueError): clock.due(0., 0., Fraction(0), 0.)
        with self.assertRaises(ValueError): ScanClock(float('inf'))

    def test_exact_period_expression(self):
        expression = ExpressionParser('1.0 / frequency').parse()
        self.assertEqual(exact_expression(expression, lambda ref: 7), Fraction(1, 7))

    def test_only_scan_guard_is_recognized(self):
        for folder, expected in [('mixing-sysml-model', 1), ('thermostat', 0),
                                 ('cruise-controller-model', 0)]:
            parser = SysMLParser(str(ROOT / 'sysml-models' / folder / 'model.sysml'))
            parser.parse()
            self.assertEqual(sum(len(list(scan_guards(body)))
                                 for _, body in parser.step_action_bodies), expected)

    def test_real_source_scan_order_types_and_first_scan(self):
        parser = SysMLParser(str(MODEL)); parser.parse()
        engine = SimulationEngine(parser); engine.initialize()
        seen = []
        def policy(inputs):
            seen.append((engine.state['system::controller::currentTimeSeconds'],
                         engine.state['system::controller::lastScanTimeSeconds']))
            return {p.name: False for part in parser.part_defs.values()
                    for action in part.action_defs if 'Neural' in action.metadata
                    for p in action.out_params}
        engine.model = policy
        self.assertFalse(seen)
        for _ in range(2402): engine.step(.1)
        self.assertEqual(len(seen), 2402)
        self.assertEqual(seen[0], (.1, .1))
        self.assertTrue(all(now == last for now, last in seen))
        for key in ('currentTimeSeconds', 'lastScanTimeSeconds'):
            self.assertIs(type(engine.state['system::controller::' + key]), float)

    def test_smv_uses_post_increment_clock_and_snapshot(self):
        module_spec = importlib.util.spec_from_file_location('mc_extract', ROOT / 'sysml-models/mc-extract.py')
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_spec.name] = module
        module_spec.loader.exec_module(module)
        parser = SysMLParser(str(MODEL)); parser.parse()
        translator = module.SMVGenerator(parser, dt='0.1')
        source = translator.generate()
        scan = next(line for line in source.splitlines() if 'scan_fires :=' in line)
        self.assertIn('controller_currentTimeSeconds + dt', scan)
        self.assertIn('(1.0 / controller_scanCycleFrequencyHz)', scan)
        block = source.split('next(controller_lastScanTimeSeconds) :=', 1)[1].split('esac;', 1)[0]
        self.assertIn(': ((controller_currentTimeSeconds + dt))', block)
        self.assertIn('(1.0 / controller_scanCycleFrequencyHz)', block)
        self.assertNotIn('epsilon', source)


if __name__ == '__main__': unittest.main()
