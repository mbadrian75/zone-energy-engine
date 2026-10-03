import unittest
from copy import deepcopy
from audit_replay_breaks import inspect
import test_replay_engine as replay_tests


class AuditTests(unittest.TestCase):
    def test_self_break_and_direction_diagnoses_do_not_mutate_state(self):
        engine = replay_tests.ReplayEngineTests().engine()
        for candle in replay_tests.candles()[:5]:
            engine.process(candle)
        pending = deepcopy(engine.state)
        current = engine._current(pending)
        pending.unattributed_breaks.extend([
            {"zone_id": current[0].id, "candle_index": 5, "close": 100},
            {"zone_id": 99, "candle_index": 5, "close": 100},
        ])
        before = deepcopy(pending)
        # Resistance origin with a bullish candle has an unaligned direction.
        rows = inspect(engine, pending, 5, replay_tests.candles()[6])
        self.assertEqual(rows[0]["diagnosis"], "origin_zone_itself_broken")
        self.assertEqual(rows[1]["diagnosis"], "candle_direction_not_aligned_with_origin")
        self.assertEqual(pending, before)

    def test_no_origin(self):
        engine = replay_tests.ReplayEngineTests().engine()
        pending = deepcopy(engine.state)
        pending.unattributed_breaks.append({"zone_id": 1, "candle_index": 0, "close": 108})
        rows = inspect(engine, pending, 0, replay_tests.candles()[0])
        self.assertEqual(rows[0]["diagnosis"], "no_open_interaction")
        self.assertIsNone(rows[0]["origin_zone_id"])


if __name__ == "__main__":
    unittest.main()
