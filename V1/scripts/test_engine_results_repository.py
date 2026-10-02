import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig
from zone_energy.data import EngineResultsRepository
from zone_energy.models import BreakRecord, Interaction, InteractionState, PriceSide, Zone, ZoneState, ZoneType


class MemoryCollection:
    def __init__(self):
        self.documents = {}

    def update_one(self, query, update, upsert):
        self.documents.setdefault(query["_id"], deepcopy(update["$setOnInsert"]))

    def find_one(self, query):
        return deepcopy(self.documents.get(query["_id"]))


class MemoryClient:
    def __init__(self):
        self.accessed = []
        self.collection = MemoryCollection()

    def __getitem__(self, name):
        self.accessed.append(name)
        return self if len(self.accessed) == 1 else self.collection


def zone_fixture():
    record = BreakRecord(9, 15, 120, 5, 2, 1, 2, 4, 1, 0.5, None, None)
    move = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                       end_index=20, distance=30, movement_time=10,
                       breaks=[record], base_energy=10)
    return Zone(1, ZoneType.SUPPORT, ZoneState.BROKEN, 99, 101, 100, 10,
                interactions=[move], created_at_index=11,
                last_external_price_side=PriceSide.BELOW)


class EngineResultsRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.client = MemoryClient()
        self.repository = EngineResultsRepository(client=self.client)

    def save(self, zones, run_id="test"):
        return self.repository.save_checkpoint(zones, run_id=run_id, symbol="XAUUSD",
            current_candle_index=1010, year_candles=1000, config=EngineConfig())

    def test_same_database_and_separate_collection(self):
        self.assertEqual(self.client.accessed, ["market_data", "zone_energy_checkpoints"])

    def test_roundtrip_restores_models_and_break_snapshots(self):
        zone = zone_fixture()
        before = deepcopy(zone)
        checkpoint_id = self.save([zone])
        self.assertEqual(self.repository.load_zones(checkpoint_id), [zone])
        document = self.repository.get_checkpoint(checkpoint_id)
        self.assertEqual(document["effective_zone_energies"], [{"zone_id": 1, "energy": 0.5}])
        self.assertEqual(document["zones"][0]["state"], "broken")
        self.assertEqual(zone, before)

    def test_repeat_save_is_idempotent(self):
        zone = zone_fixture()
        self.assertEqual(self.save([zone]), self.save([zone]))
        self.assertEqual(len(self.client.collection.documents), 1)

    def test_unknown_break_references_roundtrip_without_becoming_zero(self):
        zone = zone_fixture()
        zone.interactions[0].breaks[0] = replace(
            zone.interactions[0].breaks[0], broken_zone_energy_at_break=None,
            median_active_zone_energy_at_break=None, barrier_ratio=None,
            barrier_cost=None, break_evidence=None,
        )
        checkpoint_id = self.save([zone])
        restored = self.repository.load_zones(checkpoint_id)
        self.assertEqual(restored, [zone])
        record = restored[0].interactions[0].breaks[0]
        self.assertIsNone(record.barrier_cost)
        self.assertIsNone(record.broken_zone_energy_at_break)

    def test_conflicting_save_cannot_rewrite_checkpoint(self):
        zone = zone_fixture()
        checkpoint_id = self.save([zone])
        zone.interactions[0].base_energy = 20
        with self.assertRaises(ValueError):
            self.save([zone])
        self.assertEqual(self.repository.load_zones(checkpoint_id)[0].interactions[0].base_energy, 10)

    def test_runs_remain_separate_and_unknown_energy_remains_none(self):
        zone = zone_fixture()
        zone.interactions[0].base_energy = None
        first = self.save([zone], "first")
        second = self.save([zone], "second")
        self.assertNotEqual(first, second)
        self.assertIsNone(self.repository.get_checkpoint(first)["effective_zone_energies"][0]["energy"])

    def test_invalid_numeric_or_duplicate_data_never_writes(self):
        for condition in ("nan", "duplicate", "future"):
            zone = zone_fixture()
            if condition == "nan":
                zone.interactions[0].start_price = float("nan")
            elif condition == "future":
                zone.interactions[0].breaks[0] = BreakRecord(9, 2000, 120, 5, 2, 1, 2, 4, 1, 0.5, None, None)
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    self.save([zone, zone] if condition == "duplicate" else [zone])
                self.assertEqual(self.client.collection.documents, {})

    def test_missing_checkpoint(self):
        self.assertIsNone(self.repository.get_checkpoint("missing"))
        self.assertIsNone(self.repository.load_zones("missing"))


if __name__ == "__main__":
    unittest.main()
