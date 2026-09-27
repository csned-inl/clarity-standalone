"""Response obligations run after commands; completion cannot skip that response."""
import unittest
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "rl"), str(ROOT / "sysml-models")]
from env import SysMLEnv
from shield import SpecShield
def models_root():
    return ROOT / "sysml-models"

class ResponseTiming(unittest.TestCase):
    def environment(self):
        path = str(models_root() / 'mixing-sysml-model/model.sysml')
        env = SysMLEnv(path, dt=.1, max_steps=5000, phase=2)
        self.addCleanup(env.close)
        shield = SpecShield(path)
        initial = env.reset_with_result(seed=1833613192)
        self.assertEqual(initial.outcome, 'decision', repr(initial))
        self.assertTrue(initial.events)
        self.assertTrue(all(e.boundary == 'initialization' for e in initial.events))
        self.assertEqual(len(initial.events[-1].statuses), 4)
        return env, shield

    def test_unanswered_liveness_is_not_failed_but_wrong_response_is(self):
        env, shield = self.environment()
        _, _, done, info = env.step(0)
        self.assertTrue(done)
        self.assertEqual(info['outcome'], 'VIOLATION')
        self.assertFalse(info['statuses']['Fluid Transfer Liveness']['status'])
        self.assertTrue(any(e.boundary == 'cycle_end' and
                            e.statuses['Fluid Transfer Liveness']['status'] is False
                            for e in info['requirement_events']))

    def finish(self, incorrect_final):
        env, shield = self.environment()
        for _ in range(5000):
            final_response = env._twin.model_inputs['done']
            action = shield._requirement_action(env._twin.model_inputs)
            if final_response and incorrect_final:
                action = next(a for a, outputs in env._action_map.items()
                              if all(outputs.values()))
            _, _, done, info = env.step(action)
            if done:
                self.assertTrue(final_response)
                self.assertTrue(any(e.boundary == 'cycle_end' for e in info['requirement_events']))
                if incorrect_final:
                    self.assertEqual(info['outcome'], 'VIOLATION')
                    self.assertFalse(info['statuses']['Fluid Transfer Termination Safety']['status'])
                else:
                    self.assertEqual(info['outcome'], 'SUCCESS')
                    self.assertTrue(all(v['status'] for v in info['statuses'].values()))
                    for tank in (1, 2):
                        self.assertFalse(env._twin.engine.state[f'system::pump{tank}::isRunning'])
                return
        self.fail('completion was not reached')

    def test_final_pump_off_response_is_applied_before_success(self):
        self.finish(False)

    def test_wrong_final_response_is_counted_as_safety_violation(self):
        self.finish(True)

    def test_violation_between_decisions_is_not_overwritten(self):
        env, shield = self.environment()
        engine = env._twin.engine
        original_record = engine.record_requirements
        injected = []
        def record(boundary, source=""):
            if boundary == 'cycle_end' and not injected:
                pump = engine.state['system::pump1::isRunning']
                valve = engine.state['system::valve1::isOpen']
                engine.state['system::pump1::isRunning'] = True
                engine.state['system::valve1::isOpen'] = False
                original_record(boundary, source)
                engine.state['system::pump1::isRunning'] = pump
                engine.state['system::valve1::isOpen'] = valve
                injected.append(True)
            else:
                original_record(boundary, source)
        engine.record_requirements = record
        action = shield._requirement_action(env._twin.model_inputs)
        _, reward, done, info = env.step(action)
        self.assertTrue(done)
        self.assertEqual(reward, -1.0)
        self.assertEqual(info['outcome'], 'VIOLATION')
        self.assertFalse(info['statuses']['No Dead Heading']['status'])
        self.assertTrue(engine.requirement_statuses()['No Dead Heading']['status'])

    def test_requirement_error_is_not_accepted_as_success(self):
        env, shield = self.environment()
        engine = env._twin.engine
        original_record = engine.record_requirements
        def record(boundary, source=""):
            level = engine.state.pop('system::controller::observedLevel1')
            try:
                original_record(boundary, source)
            finally:
                engine.state['system::controller::observedLevel1'] = level
        engine.record_requirements = record
        action = shield._requirement_action(env._twin.model_inputs)
        _, reward, done, info = env.step(action)
        self.assertTrue(done)
        self.assertEqual(reward, 0.0)
        self.assertEqual(info['outcome'], 'ERROR')
        self.assertTrue(info['evaluation_errors'])

if __name__ == '__main__':
    unittest.main()
