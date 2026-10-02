import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.return_reversal_processor import ReturnReversalProcessor
from zone_energy.models import Candle, Interaction, InteractionState, Reversal, Zone, ZoneState, ZoneType


def scenario():
    zone = Zone(1, ZoneType.SUPPORT, ZoneState.ACTIVE, 100, 110, 105, 10,
                created_at_index=11)
    old = Interaction(1, 1, InteractionState.CLOSED, 105, 10,
                      end_index=15, base_energy=5)
    zone.interactions.append(old)
    zone.last_interaction_origin_index = 10
    c1 = Candle(datetime(2025, 1, 1, 10), 115, 116, 112, 113, 0)
    c2 = Candle(datetime(2025, 1, 1, 11), 113, 114, 105, 106, 0)
    c3 = Candle(datetime(2025, 1, 1, 12), 106, 116, 106, 115, 0)
    reversal = Reversal(ZoneType.SUPPORT, 105, 20, 21)
    return zone, reversal, c1, c2, c3


class ConfirmedReturnReversalProcessorTests(unittest.TestCase):
    def test_new_reaction_preserves_old_origin_and_energy(self):
        zone, reversal, c1, c2, c3 = scenario()
        old = zone.interactions[0]
        before = deepcopy(old)
        current = ReturnReversalProcessor.process_confirmed(zone, reversal, c1, c2, c3, 2, 21)
        self.assertEqual((current.start_price, current.start_index), (105, 20))
        self.assertEqual(current.state, InteractionState.OPEN)
        self.assertEqual(old, before)
        self.assertIs(zone.interactions[0], old)
        self.assertEqual(zone.last_interaction_origin_index, 20)

    def test_c3_must_be_known(self):
        zone, reversal, c1, c2, c3 = scenario()
        before = deepcopy(zone)
        with self.assertRaises(ValueError):
            ReturnReversalProcessor.process_confirmed(zone, reversal, c1, c2, c3, 2, 20)
        self.assertEqual(zone, before)

    def test_reversal_must_match_actual_pattern(self):
        zone, _, c1, c2, c3 = scenario()
        before = deepcopy(zone)
        with self.assertRaises(ValueError):
            ReturnReversalProcessor.process_confirmed(zone, Reversal(ZoneType.SUPPORT, 104, 20, 21),
                                                      c1, c2, c3, 2, 21)
        self.assertEqual(zone, before)

    def test_replay_old_origin_after_newer_reaction_is_ignored(self):
        zone, reversal, c1, c2, c3 = scenario()
        ReturnReversalProcessor.process_confirmed(zone, reversal, c1, c2, c3, 2, 21)
        newer = Reversal(ZoneType.SUPPORT, 105, 30, 31)
        ReturnReversalProcessor.process_confirmed(zone, newer, c1, c2, c3, 3, 31)
        before = deepcopy(zone)
        self.assertIsNone(ReturnReversalProcessor.process_confirmed(zone, reversal, c1, c2, c3, 4, 31))
        self.assertEqual(zone, before)

    def test_unrecorded_past_reaction_and_duplicate_id_are_rejected(self):
        for condition in ("past", "id"):
            zone, reversal, c1, c2, c3 = scenario()
            if condition == "past":
                zone.last_interaction_origin_index = 30
            before = deepcopy(zone)
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    ReturnReversalProcessor.process_confirmed(zone, reversal, c1, c2, c3,
                                                              1 if condition == "id" else 2, 31)
                self.assertEqual(zone, before)

    def test_broken_zone_has_no_new_return_interaction(self):
        zone, reversal, c1, c2, c3 = scenario()
        zone.state = ZoneState.BROKEN
        before = deepcopy(zone)
        self.assertIsNone(ReturnReversalProcessor.process_confirmed(zone, reversal, c1, c2, c3, 2, 21))
        self.assertEqual(zone, before)


if __name__ == "__main__":
    unittest.main()
