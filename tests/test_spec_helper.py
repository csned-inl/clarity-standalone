"""Threshold semantics, failed shielding, and negative scenario-bound regressions."""
import itertools
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'rl'), str(ROOT / 'sysml-models')]
from env import SysMLEnv, _extract_scenario_bounds, _walk_bounds
from shield import SpecShield, NoValidActionError, _evaluate
from sysml_parser import SysMLParser, BinaryExpr, LiteralExpr, RefExpr, UnaryExpr

MODELS = {
    'thermostat': ROOT / 'sysml-models/thermostat/model.sysml',
    'cruise': ROOT / 'sysml-models/cruise-controller-model/model.sysml',
    'mixing': ROOT / 'sysml-models/mixing-sysml-model/model.sysml',
}

def neighbors(value):
    return [math.nextafter(value, -math.inf), value, math.nextafter(value, math.inf)]

class HelperTests(unittest.TestCase):
    def assert_source_agreement(self, shield, cases):
        for observation in cases:
            expected = []
            for action, outputs in shield.action_map.items():
                value = _evaluate(shield.req_ast,
                                  {**shield.unchanging, **observation, **outputs},
                                  shield.subject_var)
                self.assertEqual(shield.is_valid(action, observation), value,
                                 (observation, action))
                if value:
                    expected.append(action)
            self.assertEqual(shield.valid_actions(observation), tuple(expected))
            for proposed in shield.action_map:
                if not expected:
                    with self.assertRaises(NoValidActionError):
                        shield.select(proposed, observation)
                else:
                    final, overridden = shield.select(proposed, observation)
                    self.assertIn(final, expected)
                    self.assertEqual(overridden, final != proposed)
                    if proposed in expected:
                        self.assertEqual(final, proposed)

    def test_thermostat_inclusive_thresholds(self):
        shield = SpecShield(str(MODELS['thermostat']))
        tolerance = shield.unchanging['toleranceCelcius']
        cases = [{'setPoint': 23., 'temperatureCelcius': temp, 'done': done}
                 for temp, done in itertools.product(
                     neighbors(23.-tolerance)+neighbors(23.+tolerance), [False, True])]
        self.assert_source_agreement(shield, cases)
        self.assertEqual(shield._requirement_action(
            {'setPoint': 23., 'temperatureCelcius': 23.-tolerance}), 1)
        self.assertEqual(shield._requirement_action(
            {'setPoint': 23., 'temperatureCelcius': 23.+tolerance}), 2)

    def test_cruise_strict_and_inclusive_thresholds(self):
        shield = SpecShield(str(MODELS['cruise']))
        tolerance = shield.unchanging['toleranceMps']
        gap = shield.unchanging['safeFollowingDistanceMeters']
        cases = [{'targetSpeed': 20., 'currentSpeedMps': speed,
                  'gapMeters': distance, 'done': done}
                 for speed, distance, done in itertools.product(
                     neighbors(20.-tolerance)+neighbors(20.+tolerance),
                     neighbors(gap), [False, True])]
        self.assert_source_agreement(shield, cases)

    def test_mixing_strict_thresholds_all_sixteen_actions(self):
        shield = SpecShield(str(MODELS['mixing']))
        cases = [{'tank1OriginalMl': 1000., 'tank2OriginalMl': 1000.,
                  'tank1TargetTransferMl': 100., 'tank2TargetTransferMl': 100.,
                  'tank1VolumeMl': v1, 'tank2VolumeMl': v2, 'done': done}
                 for v1, v2, done in itertools.product(neighbors(900.), neighbors(900.), [False, True])]
        self.assert_source_agreement(shield, cases)

    def test_unsatisfiable_requirement_errors_in_every_entry_point(self):
        source = MODELS['thermostat'].read_text().replace(
            'not (p.heaterState and p.acState)', 'p.heaterState and not p.heaterState')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'model.sysml'
            path.write_text(source)
            shield = SpecShield(str(path))
            observation = {'setPoint': 23., 'temperatureCelcius': 20., 'done': False}
            for operation in [lambda: shield(0, observation),
                              lambda: shield.select(0, observation),
                              lambda: shield._requirement_action(observation)]:
                with self.assertRaises(NoValidActionError):
                    operation()

    def test_missing_input_is_an_error(self):
        shield = SpecShield(str(MODELS['thermostat']))
        with self.assertRaises(KeyError):
            shield(0, {'setPoint': 23.})

    def test_negative_outside_temperature_bound_and_sampling(self):
        parser = SysMLParser(str(MODELS['thermostat']))
        parser.parse()
        bounds = _extract_scenario_bounds(parser)
        key = next(k for k in bounds if k.endswith('outsideTemperatureCelcius'))
        self.assertEqual(bounds[key]['lower'], -10)
        self.assertEqual(bounds[key]['upper'], 50)
        env = SysMLEnv(str(MODELS['thermostat']), dt=1., rng_seed=42)
        try:
            samples = [env._sample_scenario()[key] for _ in range(100)]
            self.assertTrue(any(value < 0 for value in samples))
            self.assertTrue(all(-10 <= value <= 50 for value in samples))
        finally:
            env.close()

    def test_zero_lower_bound_stays_stronger_than_negative_bound(self):
        inputs = {'system::outside': {'lower': None, 'upper': None}}
        _walk_bounds(BinaryExpr('>=', RefExpr(['outside']), LiteralExpr(0)), inputs, 'system')
        _walk_bounds(BinaryExpr('>=', RefExpr(['outside']), UnaryExpr('-', LiteralExpr(10))),
                     inputs, 'system')
        self.assertEqual(inputs['system::outside']['lower'], 0)

if __name__ == '__main__':
    unittest.main()
