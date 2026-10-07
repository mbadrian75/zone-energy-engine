import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from datetime import datetime
from zone_energy.config import EngineConfig
from zone_energy.engine.break_processor import BreakProcessor
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.engine.zone_creation_processor import ZoneCreationProcessor
from zone_energy.models import Candle, Reversal, ZoneState, ZoneType


def create(zones, zone_id, kind, price, index):
    return ZoneCreationProcessor.process(zones, zone_id, zone_id,
        Reversal(kind, price, index, index + 1), price - 1, price + 1, index + 1)


class BootstrapLifecycleTests(unittest.TestCase):
    def test_unknown_first_zone_breaks_and_next_move_becomes_scoreable(self):
        zones = []
        baseline = create(zones, 1, ZoneType.SUPPORT, 100, 10)
        origin = create(zones, 2, ZoneType.RESISTANCE, 130, 20)
        interaction = origin.interactions[0]
        snapshot = MarketEnergySnapshotCalculator(EngineConfig()).capture(zones, 25, 1000)
        self.assertIsNone(snapshot.median_active_energy)
        candle = Candle(datetime(2025, 1, 1), 95, 96, 89, 90, 0)
        records = BreakProcessor(EngineConfig()).process(interaction, origin, zones, candle, 25, 1000)
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertIsNone(record.broken_zone_energy_at_break)
        self.assertIsNone(record.median_active_zone_energy_at_break)
        self.assertIsNone(record.barrier_ratio)
        self.assertIsNone(record.barrier_cost)
        self.assertIsNone(record.break_evidence)
        self.assertEqual(record.persistence, 0.5)
        self.assertEqual(baseline.state, ZoneState.BROKEN)
        create(zones, 3, ZoneType.SUPPORT, 80, 30)
        self.assertAlmostEqual(interaction.base_energy, 50 / 30)
        self.assertIs(interaction.breaks[0], record)
        self.assertIsNone(record.break_evidence)
        self.assertIsNone(baseline.interactions[0].base_energy)
        snapshot = MarketEnergySnapshotCalculator(EngineConfig()).capture(zones, 31, 1000)
        self.assertGreater(snapshot.median_active_energy, 0)

    def test_initial_unknown_energy_does_not_poison_later_market_reference(self):
        zones = []
        create(zones, 1, ZoneType.SUPPORT, 100, 10)
        scored = create(zones, 2, ZoneType.RESISTANCE, 130, 20)
        create(zones, 3, ZoneType.SUPPORT, 100, 30)
        snapshot = MarketEnergySnapshotCalculator(EngineConfig()).capture(zones, 31, 1000)
        energy = EffectiveZoneEnergyCalculator(EngineConfig()).calculate(scored, 31, 1000)
        self.assertIsNone(snapshot.zone_energies[0][1])
        self.assertAlmostEqual(snapshot.median_active_energy, energy)


if __name__ == "__main__":
    unittest.main()
