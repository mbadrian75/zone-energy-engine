"""Standalone fake-Mongo contract tests; never require a live database."""
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from mongo_result_repository import MongoV2ResultRepository

UTC = timezone.utc


class FakeCollection:
    def __init__(self):
        self.docs = {}
        self.indexes = []
    def create_index(self, columns, unique=False):
        self.indexes.append((columns, unique))
    def insert_one(self, item):
        if item["_id"] in self.docs:
            raise ValueError("duplicate key")
        self.docs[item["_id"]] = item.copy()
    def insert_many(self, items, ordered=True):
        for item in items:
            self.insert_one(item)
    def update_one(self, query, update):
        doc = self.docs.get(query["_id"])
        if doc is None or ("status" in query and doc["status"] != query["status"]):
            return SimpleNamespace(matched_count=0)
        for key, delta in update.get("$inc", {}).items():
            doc[key] += delta
        doc.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1)


class FakeDatabase:
    def __init__(self):
        self.collections = {}
    def __getitem__(self, name):
        return self.collections.setdefault(name, FakeCollection())


class FakeClient:
    def __init__(self):
        self.db = FakeDatabase()
        self.collections = self.db.collections
    def __getitem__(self, database):
        return self.db


def point(hour=1, energy=None):
    at = datetime(2025, 1, 1, hour, tzinfo=UTC)
    empty = {"candle_index": None, "median_active_energy": None, "zones": []}
    h1 = {"candle_index": hour - 1, "median_active_energy": energy, "zones": [
        {"zone_id": "H1:1", "local_zone_id": 1, "type": "support",
         "state": "active", "lower_price": 100.0, "upper_price": 102.0,
         "creation_index": 0, "created_at_index": 0,
         "interaction_count": 1, "effective_energy": energy}
    ]}
    return SimpleNamespace(at=at, zones={"H1": h1, "H4": empty, "D1": empty},
        last_closed_at={"H1": at, "H4": None, "D1": None})


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.repo = MongoV2ResultRepository(client=self.client)
        self.begin()
    def begin(self):
        self.repo.begin_run(run_id="sample", start=datetime(2025,1,1,tzinfo=UTC),
            end=datetime(2025,1,3,tzinfo=UTC),
            year_candles={"H1": 5933, "H4": 1601, "D1": 313})

    def test_catalog_once_and_two_immutable_snapshots(self):
        self.assertEqual(self.repo.append_points([point(1), point(2, 5)], batch_size=1), 2)
        self.assertEqual(self.repo.finish_run(), 2)
        db = self.client.collections
        self.assertEqual(len(db["zone_energy_v2_zones"].docs), 1)
        self.assertEqual(len(db["zone_energy_v2_snapshots"].docs), 2)
        self.assertEqual(db["zone_energy_v2_runs"].docs["sample"]["status"], "completed")
        self.assertEqual(db["zone_energy_v2_runs"].docs["sample"]["snapshot_count"], 2)
        snapshots = list(db["zone_energy_v2_snapshots"].docs.values())
        self.assertIsNone(snapshots[0]["timeframes"]["H1"]["zones"][0]["effective_energy"])
        self.assertEqual(snapshots[1]["timeframes"]["H1"]["zones"][0]["effective_energy"], 5)
        self.assertNotIn("lower_price", snapshots[1]["timeframes"]["H1"]["zones"][0])

    def test_duplicate_run_rejected_without_overwriting(self):
        other = MongoV2ResultRepository(client=self.client)
        with self.assertRaisesRegex(ValueError, "duplicate key"):
            other.begin_run(run_id="sample", start=datetime(2025,1,1,tzinfo=UTC),
                end=datetime(2025,1,3,tzinfo=UTC),
                year_candles={"H1": 5933, "H4": 1601, "D1": 313})
        self.assertEqual(len(self.client.collections["zone_energy_v2_runs"].docs), 1)

    def test_future_bar_rejected(self):
        p = point()
        p.last_closed_at["H4"] = p.at + timedelta(hours=1)
        with self.assertRaisesRegex(ValueError, "Future"):
            self.repo.append_points([p])
        self.assertEqual(len(self.client.collections["zone_energy_v2_snapshots"].docs), 0)

    def test_repeated_decision_rejected(self):
        with self.assertRaisesRegex(ValueError, "strictly increase"):
            self.repo.append_points([point(), point()])
        self.assertEqual(len(self.client.collections["zone_energy_v2_snapshots"].docs), 0)

    def test_completed_run_cannot_accept_more_decisions(self):
        self.repo.append_points([point()])
        self.repo.finish_run()
        with self.assertRaisesRegex(RuntimeError, "running run"):
            self.repo.append_points([point(2)])
        self.assertEqual(len(self.client.collections["zone_energy_v2_snapshots"].docs), 1)

    def test_duplicate_zone_within_snapshot_rejected(self):
        p = point()
        p.zones["H1"]["zones"].append(dict(p.zones["H1"]["zones"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate zone"):
            self.repo.append_points([p])
        self.assertEqual(len(self.client.collections["zone_energy_v2_snapshots"].docs), 0)

    def test_failure_status_and_empty_completion(self):
        with self.assertRaisesRegex(ValueError, "zero decisions"):
            self.repo.finish_run()
        self.repo.fail_run(RuntimeError("hidden details"))
        doc = self.client.collections["zone_energy_v2_runs"].docs["sample"]
        self.assertEqual(doc["status"], "failed")
        self.assertEqual(doc["error_type"], "RuntimeError")
        self.assertNotIn("hidden details", str(doc))


if __name__ == "__main__":
    unittest.main()
