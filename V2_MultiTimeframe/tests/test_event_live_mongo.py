"""Opt-in real MongoDB contract test. Retains dedicated run documents for audit."""
import os
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from mongo_event_repository import MongoEventRepository, MongoEventReader
from test_mongo_result_repository import point


@unittest.skipUnless(os.environ.get("ZONE_ENERGY_LIVE_MONGO_TEST") == "1",
                     "Set ZONE_ENERGY_LIVE_MONGO_TEST=1 for real MongoDB contract test")
class LiveMongoTests(unittest.TestCase):
    def test_indexes_binary_roundtrip_and_duplicate_run(self):
        from pymongo.errors import DuplicateKeyError
        repo = MongoEventRepository(mongo_uri=os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/"),
                                   database=os.environ.get("ZONE_ENERGY_TEST_DATABASE", "market_data"))
        run_id = "live-contract-" + uuid4().hex
        settings = dict(run_id=run_id, start=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        end=datetime(2025, 2, 1, tzinfo=timezone.utc),
                        year_candles={"H1": 5933, "H4": 1601, "D1": 313})
        try:
            repo.begin_run(**settings)
            def points():
                for p in (point(1), point(2, 5)):
                    repo.observe("H1", p.at, p.zones["H1"])
                    yield p
            repo.append_points(points(), batch_size=1)
            repo.finish_run()
            reader = MongoEventReader(repo, run_id)
            self.assertEqual(reader.reconstruct(point().at, from_events=True)["timeframes"], point().zones)
            self.assertEqual(reader.reconstruct(point(2).at, from_events=True), reader.reconstruct(point(2).at))
            second = MongoEventRepository(client=repo.client, database=os.environ.get("ZONE_ENERGY_TEST_DATABASE", "market_data"))
            with self.assertRaises(DuplicateKeyError):
                second.begin_run(**settings)
            event = repo.events.find_one({"run_id": run_id})
            event.pop("_id")
            with self.assertRaises(DuplicateKeyError):
                repo.events.insert_one(event)
            snapshot = repo.snapshots.find_one({"run_id": run_id})
            snapshot.pop("_id")
            with self.assertRaises(DuplicateKeyError):
                repo.snapshots.insert_one(snapshot)
            for collection in (repo.events, repo.snapshots, repo.runs):
                self.assertTrue(any(i.get("unique") and ("schema_version", 1) in i["key"].items()
                                    for i in collection.index_information().values()))
            print("Retained MongoDB contract run:", run_id)
        except BaseException as exc:
            repo.fail_run(exc)
            raise
        finally:
            repo.close()


if __name__ == "__main__":
    unittest.main()
