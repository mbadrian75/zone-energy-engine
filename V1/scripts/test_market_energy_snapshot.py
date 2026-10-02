import sys
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig
from zone_energy.engine.break_record_factory import BreakRecordFactory
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType


def make_zone(zone_id, base_energy):
    zone = Zone(zone_id, ZoneType.RESISTANCE, ZoneState.ACTIVE, 100, 110, 110, 0,
                created_at_index=1)
    zone.interactions = [Interaction(zone_id, zone_id, InteractionState.CLOSED,
                                    110, 0, end_index=10, base_energy=base_energy)]
    return zone


class MarketEnergySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.calculator = MarketEnergySnapshotCalculator(EngineConfig())

    def test_median_resists_outlier_and_decays_at_capture_time(self):
        zones = [make_zone(1, 20), make_zone(2, 40), make_zone(3, 20000)]
        snapshot = self.calculator.capture(zones, 1000, 1000)
        self.assertEqual(snapshot.median_active_energy, 2)
        self.assertEqual(snapshot.reference_for_break(1), (1, 2))

    def test_even_population_and_broken_exclusion(self):
        zones = [make_zone(1, 20), make_zone(2, 40), make_zone(3, 100)]
        zones[2].state = ZoneState.BROKEN
        snapshot = self.calculator.capture(zones, 1000, 1000)
        self.assertAlmostEqual(snapshot.median_active_energy, 1.5)
        with self.assertRaises(ValueError):
            snapshot.reference_for_break(3)

    def test_zero_energy_participates_but_zero_median_cannot_divide(self):
        snapshot = self.calculator.capture([make_zone(1, 0), make_zone(2, 40)], 1000, 1000)
        self.assertEqual(snapshot.reference_for_break(1), (0, 1))
        snapshot = self.calculator.capture([make_zone(1, 0)], 1000, 1000)
        self.assertEqual(snapshot.median_active_energy, 0)
        with self.assertRaises(ValueError):
            snapshot.reference_for_break(1)

    def test_empty_or_undefined_population_has_no_median(self):
        self.assertIsNone(self.calculator.capture([], 1000, 1000).median_active_energy)
        snapshot = self.calculator.capture([make_zone(1, 20), make_zone(2, None)], 1000, 1000)
        self.assertIsNone(snapshot.median_active_energy)
        with self.assertRaises(ValueError):
            snapshot.reference_for_break(1)
        with self.assertRaises(ValueError):
            snapshot.reference_for_break(2)

    def test_snapshot_remains_immutable_after_live_changes(self):
        zone = make_zone(1, 20)
        snapshot = self.calculator.capture([zone], 1000, 1000)
        zone.state = ZoneState.BROKEN
        zone.interactions[0].base_energy = 999
        self.assertEqual(snapshot.reference_for_break(1), (1, 1))
        with self.assertRaises(FrozenInstanceError):
            snapshot.candle_index = 1001
        with self.assertRaises(TypeError):
            snapshot.zone_energies[0] = (1, 999)

    def test_multiple_breaks_share_reference_regardless_of_processing_order(self):
        factory = BreakRecordFactory(EngineConfig())
        mover = Interaction(10, 10, InteractionState.OPEN, 95, 990,
                            previous_distance=20, previous_movement_time=10)
        candle = Candle(datetime(2025, 1, 1), 111, 116, 110.5, 115, 0)
        results = []
        for order in ((1, 2), (2, 1)):
            zones = {1: make_zone(1, 20), 2: make_zone(2, 40)}
            snapshot = self.calculator.capture(zones.values(), 1000, 1000)
            records = {}
            for zone_id in order:
                record = factory.create_from_snapshot(zones[zone_id], mover, candle, 1000, snapshot)
                records[zone_id] = record
                zones[zone_id].state = ZoneState.BROKEN
            self.assertTrue(all(record.median_active_zone_energy_at_break == 1.5
                                for record in records.values()))
            results.append(records)
        self.assertEqual(results[0], results[1])

    def test_factory_rejects_snapshot_from_other_candle(self):
        zone = make_zone(1, 20)
        snapshot = self.calculator.capture([zone], 1000, 1000)
        mover = Interaction(10, 10, InteractionState.OPEN, 95, 990,
                            previous_movement_time=10)
        candle = Candle(datetime(2025, 1, 1), 111, 116, 110.5, 115, 0)
        with self.assertRaises(ValueError):
            BreakRecordFactory(EngineConfig()).create_from_snapshot(zone, mover, candle, 1001, snapshot)

    def test_duplicate_zones_and_invalid_empty_input_are_rejected(self):
        zone = make_zone(1, 20)
        with self.assertRaises(ValueError):
            self.calculator.capture([zone, zone], 1000, 1000)
        with self.assertRaises(ValueError):
            self.calculator.capture([], 1000, 0)

    def test_large_even_median_remains_finite(self):
        zones = [make_zone(1, 1.7e308), make_zone(2, 1.7e308)]
        snapshot = self.calculator.capture(zones, 10, 1000)
        self.assertGreater(snapshot.median_active_energy, 1e308)


if __name__ == "__main__":
    unittest.main()
