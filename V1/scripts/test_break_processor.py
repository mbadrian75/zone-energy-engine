import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig
from zone_energy.engine.break_processor import BreakProcessor
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType


def make_zone(zone_id, kind, lower, upper, base):
    zone = Zone(zone_id, kind, ZoneState.ACTIVE, lower, upper, lower, 0, created_at_index=1)
    zone.interactions = [Interaction(zone_id, zone_id, InteractionState.CLOSED,
                                    lower, 0, end_index=10, base_energy=base)]
    return zone


def scenario(bearish=False):
    origin_kind = ZoneType.RESISTANCE if bearish else ZoneType.SUPPORT
    target_kind = ZoneType.SUPPORT if bearish else ZoneType.RESISTANCE
    origin = make_zone(1, origin_kind, 90, 95, 60)
    first = make_zone(2, target_kind, 100, 110, 20)
    second = make_zone(3, target_kind, 101, 111, 40)
    current = Interaction(10, 1, InteractionState.OPEN, 95, 990,
                          previous_distance=20, previous_movement_time=10)
    origin.interactions.append(current)
    candle = (Candle(datetime(2025, 1, 1), 99, 99.5, 94, 95, 0) if bearish else
              Candle(datetime(2025, 1, 1), 112, 116, 111.5, 115, 0))
    return origin, first, second, current, candle


class BreakProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processor = BreakProcessor(EngineConfig())

    def test_two_breaks_share_prebreak_median_in_both_directions(self):
        for bearish in (False, True):
            with self.subTest(bearish=bearish):
                origin, first, second, current, candle = scenario(bearish)
                bases = [zone.interactions[0].base_energy for zone in (origin, first, second)]
                records = self.processor.process(current, origin, [origin, first, second], candle, 1000, 1000)
                self.assertEqual(len(records), 2)
                self.assertEqual(current.breaks, records)
                self.assertTrue(all(record.median_active_zone_energy_at_break == 2 for record in records))
                self.assertEqual([record.barrier_ratio for record in records], [0.5, 1])
                self.assertEqual((first.state, second.state), (ZoneState.BROKEN, ZoneState.BROKEN))
                self.assertEqual(origin.state, ZoneState.ACTIVE)
                self.assertEqual([zone.interactions[0].base_energy for zone in (origin, first, second)], bases)
                self.assertEqual(first.type, ZoneType.SUPPORT if bearish else ZoneType.RESISTANCE)

    def test_input_order_has_no_effect(self):
        results = []
        for reverse in (False, True):
            origin, first, second, current, candle = scenario()
            history = [origin, first, second]
            if reverse:
                history.reverse()
            results.append(self.processor.process(current, origin, iter(history), candle, 1000, 1000))
        self.assertEqual(results[0], results[1])

    def test_retry_does_not_duplicate_breaks(self):
        origin, first, second, current, candle = scenario()
        history = [origin, first, second]
        self.processor.process(current, origin, history, candle, 1000, 1000)
        self.assertEqual(self.processor.process(current, origin, history, candle, 1000, 1000), [])
        self.assertEqual(len(current.breaks), 2)

    def test_no_valid_break_leaves_state_unchanged(self):
        origin, first, second, current, _ = scenario()
        candle = Candle(datetime(2025, 1, 1), 105, 120, 104, 105, 0)
        history = [origin, first, second]
        before = deepcopy(history)
        self.assertEqual(self.processor.process(current, origin, history, candle, 1000, 1000), [])
        self.assertEqual(history, before)

    def test_undefined_zone_energy_records_break_without_blocking(self):
        origin, first, second, current, candle = scenario()
        second.interactions[0].base_energy = None
        history = [origin, first, second]
        records = self.processor.process(current, origin, history, candle, 1000, 1000)
        self.assertEqual(len(records), 2)
        self.assertIsNotNone(records[0].break_evidence)
        self.assertIsNone(records[1].broken_zone_energy_at_break)
        self.assertIsNone(records[1].break_evidence)
        self.assertEqual(second.state, ZoneState.BROKEN)
        self.assertIsNone(second.interactions[0].base_energy)

    def test_failure_on_second_record_keeps_first_break_uncommitted(self):
        origin, first, second, current, _ = scenario()
        second.lower_price = 0
        second.upper_price = 1e-308
        candle = Candle(datetime(2025, 1, 1), 1e308, 1.2e308, 1e308, 1.1e308, 0)
        history = [origin, first, second]
        before = deepcopy(history)
        with self.assertRaises(ValueError):
            self.processor.process(current, origin, history, candle, 1000, 1000)
        self.assertEqual(history, before)

    def test_invalid_origin_closed_move_and_future_time_are_rejected(self):
        for invalid in ("owner", "closed", "future", "missing_origin"):
            origin, first, second, current, candle = scenario()
            history = [origin, first, second]
            if invalid == "owner":
                current.zone_id = 99
            elif invalid == "closed":
                current.state = InteractionState.CLOSED
            elif invalid == "future":
                current.start_index = 1001
            else:
                history.remove(origin)
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.processor.process(current, origin, history, candle, 1000, 1000)
                self.assertEqual(current.breaks, [])

    def test_same_candle_cannot_be_processed_in_separate_batches(self):
        origin, first, second, current, candle = scenario()
        self.processor.process(current, origin, [origin, first], candle, 1000, 1000)
        with self.assertRaises(ValueError):
            self.processor.process(current, origin, [origin, first, second], candle, 1000, 1000)
        self.assertEqual(second.state, ZoneState.ACTIVE)
        self.assertEqual(len(current.breaks), 1)


if __name__ == "__main__":
    unittest.main()
