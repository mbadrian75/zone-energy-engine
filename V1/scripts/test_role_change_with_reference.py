import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.role_change_processor import RoleChangeProcessor
from zone_energy.models import Candle, Interaction, InteractionState, PriceSide, Reversal, Zone, ZoneState, ZoneType


def scenario(old_kind=ZoneType.SUPPORT, referenced=False):
    support = old_kind == ZoneType.SUPPORT
    new_kind = ZoneType.RESISTANCE if support else ZoneType.SUPPORT
    side = PriceSide.BELOW if support else PriceSide.ABOVE
    zone = Zone(1, old_kind, ZoneState.BROKEN, 100, 110, 100, 10,
                created_at_index=11, last_external_price_side=side)
    zone.interactions = [Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                                    end_index=14, base_energy=5)]
    zone.last_interaction_origin_index = 10
    source_price = 90 if support else 130
    source = Zone(2, old_kind, ZoneState.ACTIVE, source_price - 1, source_price + 1,
                  source_price, 15, created_at_index=16)
    prices = ((103, 106, 101, 104), (104, 108, 102, 103), (103, 105, 98, 99)) if support else (
        (107, 109, 104, 106), (106, 108, 102, 107), (107, 112, 105, 111))
    candles = [Candle(datetime(2025, 1, 1, hour), *values, 0)
               for hour, values in zip((10, 11, 12), prices)]
    reversal = Reversal(new_kind, 108 if support else 102, 20, 21)
    if referenced:
        source.interactions.append(Interaction(2, source.id, InteractionState.CLOSED, source_price, 15,
            end_price=reversal.extreme_price, end_index=20,
            distance=abs(source_price-reversal.extreme_price), movement_time=5))
    return zone, source, reversal, candles


class RoleChangeWithReferenceTests(unittest.TestCase):
    def test_both_roles_start_referenced_reaction_and_preserve_history(self):
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            zone, source, reversal, candles = scenario(kind, referenced=True)
            old = zone.interactions[0]
            old_before = deepcopy(old)
            boundaries = (zone.lower_price, zone.upper_price)
            with self.subTest(kind=kind):
                reaction = RoleChangeProcessor.process_with_reference(
                    zone, reversal, *candles, 3, 21, [zone, source])
                self.assertEqual(zone.type, reversal.type)
                self.assertEqual(zone.state, ZoneState.ACTIVE)
                self.assertEqual((zone.lower_price, zone.upper_price), boundaries)
                self.assertEqual((reaction.previous_distance, reaction.previous_movement_time),
                                 (18 if kind == ZoneType.SUPPORT else 28, 5))
                self.assertEqual((reaction.start_index, reaction.start_price), (20, reversal.extreme_price))
                self.assertIs(zone.interactions[0], old)
                self.assertEqual(old, old_before)

    def test_unconfirmed_reversal_does_not_change_role(self):
        zone, source, reversal, candles = scenario(referenced=True)
        before = deepcopy(zone)
        with self.assertRaises(ValueError):
            RoleChangeProcessor.process_with_reference(zone, reversal, *candles, 3, 20, [zone, source])
        self.assertEqual(zone, before)

    def test_failed_reference_does_not_reactivate_zone(self):
        zone, source, reversal, candles = scenario(referenced=True)
        source.interactions[0].distance = 0
        before = deepcopy(zone)
        with self.assertRaises(ValueError):
            RoleChangeProcessor.process_with_reference(zone, reversal, *candles, 3, 21, [zone, source])
        self.assertEqual(zone, before)

    def test_wrong_approach_side_has_no_effect(self):
        zone, source, reversal, candles = scenario(referenced=True)
        zone.last_external_price_side = PriceSide.ABOVE
        before = deepcopy(zone)
        self.assertIsNone(RoleChangeProcessor.process_with_reference(zone, reversal, *candles, 3, 21, [zone, source]))
        self.assertEqual(zone, before)

    def test_replay_has_no_extra_reaction(self):
        zone, source, reversal, candles = scenario(referenced=True)
        RoleChangeProcessor.process_with_reference(zone, reversal, *candles, 3, 21, [zone, source])
        before = deepcopy(zone)
        self.assertIsNone(RoleChangeProcessor.process_with_reference(zone, reversal, *candles, 4, 21, [zone, source]))
        self.assertEqual(zone, before)

    def test_duplicate_origin_does_not_flip_role_without_new_reaction(self):
        zone, source, reversal, candles = scenario(referenced=True)
        zone.interactions.append(Interaction(3, 1, InteractionState.OPEN, reversal.extreme_price, 20))
        before = deepcopy(zone)
        self.assertIsNone(RoleChangeProcessor.process_with_reference(zone, reversal, *candles, 4, 21, [zone, source]))
        self.assertEqual(zone, before)

    def test_legacy_negative_id_failure_is_atomic(self):
        zone, _, reversal, candles = scenario(referenced=True)
        before = deepcopy(zone)
        with self.assertRaises(ValueError):
            RoleChangeProcessor.process(zone, reversal, *candles, -1)
        self.assertEqual(zone, before)


if __name__ == "__main__":
    unittest.main()
