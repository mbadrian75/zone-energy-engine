import unittest
from trace_replay_interaction import capture_references, PreviousMoveResolver
from test_previous_move_resolver import zone, movement
from zone_energy.models import ZoneType
from test_return_move_reference import incoming


class ReferenceTraceTests(unittest.TestCase):
    def test_capture_preserves_historical_role_and_resolver_behavior(self):
        origin = zone(304, ZoneType.SUPPORT, 3300, 2733)
        source = zone(333, ZoneType.RESISTANCE, 3380.272, 3523)
        reference = incoming(source, 3380.035, 3565)
        move = movement(304, 986, 3380.035, 3565)
        original = PreviousMoveResolver.resolve
        with capture_references(986) as history:
            self.assertIs(PreviousMoveResolver.resolve(move, origin, [origin, source]), reference)
            PreviousMoveResolver.resolve(move, origin, [origin, source])
            self.assertEqual(len(history), 1)
            self.assertAlmostEqual(history[0]['previous_distance'], .237)
            self.assertEqual(history[0]['previous_movement_time'], 42)
            source.type = ZoneType.SUPPORT
            self.assertEqual(history[0]['source']['interaction_id'], reference.id)
            self.assertEqual(history[0]['source']['start_index'], 3523)
        self.assertIs(PreviousMoveResolver.resolve, original)

    def test_restores_resolver_after_failure_and_ignores_other_ids(self):
        original = PreviousMoveResolver.resolve
        origin = zone(1, ZoneType.SUPPORT, 100, 10)
        with self.assertRaises(RuntimeError):
            with capture_references(986) as history:
                move = movement(1, 2, 100, 10)
                PreviousMoveResolver.resolve(move, origin, [origin])
                self.assertEqual(history, [])
                raise RuntimeError('stop')
        self.assertIs(PreviousMoveResolver.resolve, original)


if __name__ == '__main__':
    unittest.main()
