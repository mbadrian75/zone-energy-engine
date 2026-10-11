import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest

from mongo_event_repository import MongoEventRepository, MongoEventReader, PREFIX
from multi_timeframe_replay import MultiTimeframeReplay, ClosedBar
from test_mongo_result_repository import FakeClient, FakeCollection, point
from validate_event_run import validate, require_validated_smoke


def matches(doc, query):
    for key, value in query.items():
        if isinstance(value, dict):
            if "$lte" in value and doc.get(key) > value["$lte"]:
                return False
        elif doc.get(key) != value:
            return False
    return True


class Cursor(list):
    def sort(self, key, direction):
        return Cursor(sorted(self, key=lambda d: d[key], reverse=direction < 0))


class Collection(FakeCollection):
    fail_after = None
    fail_update = False

    def find(self, query):
        return Cursor(deepcopy(d) for d in self.docs.values() if matches(d, query))

    def find_one(self, query):
        return next(iter(self.find(query)), None)

    def insert_many(self, items, ordered=True):
        for i, item in enumerate(items):
            if self.fail_after == i:
                raise OSError("injected partial insert")
            self.insert_one(item)

    def update_one(self, query, update):
        if self.fail_update:
            raise OSError("injected marker failure")
        if query["_id"] not in self.docs or not matches(self.docs[query["_id"]], query):
            return SimpleNamespace(matched_count=0)
        return super().update_one(query, update)


def client():
    c = FakeClient()
    for name in ("runs", "events", "snapshots"):
        c.collections[PREFIX + name] = Collection()
    return c


class EventTests(unittest.TestCase):
    def setUp(self):
        self.client = client()
        self.repo = MongoEventRepository(client=self.client, event_batch_size=2)
        self.begin(self.repo)

    def begin(self, repo, run_id="sample"):
        repo.begin_run(run_id=run_id, start=datetime(2025, 1, 1, tzinfo=timezone.utc),
                       end=datetime(2025, 2, 1, tzinfo=timezone.utc),
                       year_candles={"H1": 5933, "H4": 1601, "D1": 313})

    def points(self, points):
        for p in points:
            self.repo.observe("H1", p.at, p.zones["H1"])
            yield p

    def reader(self):
        return MongoEventReader(self.repo, "sample")

    def test_changes_null_and_reconstruction(self):
        ps = [point(1), point(2, 5), point(3, 5), point(4, 0)]
        ps[-1].zones["H1"]["zones"][0].update(type="resistance", state="broken", interaction_count=2)
        self.repo.append_points(self.points(ps), batch_size=2)
        self.repo.finish_run()
        self.assertEqual(self.repo.count, 4)
        events = list(self.repo.events.docs.values())
        self.assertEqual(len(events), 3)
        self.assertEqual(set(events[-1]["changed_fields"]), {"effective_energy", "type", "state", "interaction_count"})
        for p in ps:
            body = self.reader().reconstruct(p.at, from_events=True)
            self.assertEqual(body["timeframes"], p.zones)
            self.assertEqual(body, self.reader().reconstruct(p.at))
        self.assertIsNone(self.reader().reconstruct(ps[0].at)["timeframes"]["H1"]["zones"][0]["effective_energy"])
        with self.assertRaises(RuntimeError):
            self.repo.append_points([])
        self.assertEqual(set(self.client.collections), {PREFIX + x for x in ("runs", "events", "snapshots")})

    def test_duplicate_run_never_overwrites(self):
        other = MongoEventRepository(client=self.client)
        with self.assertRaises(ValueError):
            self.begin(other)
        other.fail_run(ValueError())
        self.assertEqual(self.repo.runs.docs["sample"]["status"], "running")

    def test_partial_snapshot_insert_and_poison(self):
        self.repo.snapshots.fail_after = 1
        with self.assertRaises(OSError):
            self.repo.append_points(self.points([point(1), point(2, 5)]), batch_size=2)
        self.assertEqual(self.repo.runs.docs["sample"]["decision_count"], 0)
        self.assertEqual(len(self.repo.snapshots.docs), 1)
        with self.assertRaises(RuntimeError):
            self.repo.finish_run()
        with self.assertRaises(RuntimeError):
            self.reader().reconstruct(point().at)
        self.repo.fail_run(OSError())
        self.assertEqual(self.repo.runs.docs["sample"]["status"], "failed")

    def test_event_insert_failure_blocks_completion(self):
        self.repo.events.fail_after = 1
        with self.assertRaises(OSError):
            self.repo.append_points(self.points([point(1), point(2, 5)]))
        self.assertEqual(len(self.repo.snapshots.docs), 0)
        with self.assertRaises(RuntimeError):
            self.repo.observe("H1", point(3).at, point(3).zones["H1"])

    def test_marker_failure_blocks_completion(self):
        self.repo.runs.fail_update = True
        with self.assertRaises(OSError):
            self.repo.append_points(self.points([point()]))
        with self.assertRaises(RuntimeError):
            self.repo.finish_run()

    def test_unobserved_or_future_decision_rejected(self):
        with self.assertRaises(ValueError):
            self.repo.append_points([point()])

    def test_static_change_and_disappearing_zone_rejected(self):
        for mutation in ("static", "disappear"):
            r = MongoEventRepository(client=self.client)
            self.begin(r, mutation)
            r.observe("H1", point().at, point().zones["H1"])
            p = point(2)
            if mutation == "static":
                p.zones["H1"]["zones"][0]["lower_price"] = 99
            else:
                p.zones["H1"]["zones"] = []
            with self.assertRaises(ValueError):
                r.observe("H1", p.at, p.zones["H1"])

    def test_future_events_do_not_change_prefix(self):
        self.repo.append_points(self.points([point(1), point(2, 5)]), batch_size=1)
        self.repo.finish_run()
        before = self.reader().reconstruct(point().at, from_events=True)
        self.assertIsNone(before["timeframes"]["H1"]["zones"][0]["effective_energy"])
        self.assertEqual(before, self.reader().reconstruct(point().at))

    def test_checksum_and_missing_event_detection(self):
        self.repo.append_points(self.points([point()]))
        self.repo.finish_run()
        event = next(iter(self.repo.events.docs))
        del self.repo.events.docs[event]
        with self.assertRaises(ValueError):
            self.reader().reconstruct(point().at, from_events=True)
        doc = next(iter(self.repo.snapshots.docs.values()))
        doc["sha256"] = "bad"
        with self.assertRaises(ValueError):
            self.reader().reconstruct(point().at)

    def test_january_2025_all_decisions_equivalent(self):
        fixture = Path(__file__).resolve().parents[1] / "v2-smoke-2025-01.jsonl"
        def decisions():
            with fixture.open(encoding="utf-8") as f:
                for line in f:
                    body = json.loads(line)
                    p = SimpleNamespace(at=datetime.fromisoformat(body["decision_at"]), zones=body["timeframes"],
                        last_closed_at={tf: datetime.fromisoformat(t) if t else None for tf, t in body["last_closed_at"].items()})
                    # JSONL only observes at H1: it cannot prove changes between
                    # H1 decisions. Replay observer integration is tested separately.
                    observations = [(t, {"D1": 0, "H4": 1, "H1": 2}[tf], tf)
                        for tf, t in p.last_closed_at.items()
                        if t is not None and t.replace(tzinfo=None) != self.repo.observed_at[tf]]
                    for t, _, tf in sorted(observations):
                        self.repo.observe(tf, t, p.zones[tf])
                    yield p
        self.repo.append_points(decisions(), batch_size=25)
        self.repo.finish_run()
        report = validate(self.repo, "sample", fixture)
        self.assertEqual(report["decisions"], 504)
        self.assertEqual(report["zones"], 116)
        self.assertLess(report["compressed_bytes"], report["raw_bytes"])
        self.assertEqual(require_validated_smoke(self.repo, "sample", {"H1": 5933, "H4": 1601, "D1": 313}), report)
        print("January schema-2 equivalence:", json.dumps(report, sort_keys=True))

    def test_closed_bar_observer_records_gap_changes_and_excludes_tail(self):
        class Engine:
            def __init__(self):
                self.states = deepcopy(self_repo.states)
            def on_closed_bar(self, tf, bar):
                state = deepcopy(point(bar.closed_at.hour, bar.close).zones["H1"])
                state["zones"][0]["zone_id"] = tf + ":1"
                self.states[tf] = state
            def snapshot(self, tf):
                return self.states[tf]
        self_repo = self.repo
        def bar(tf, hour):
            return ClosedBar(tf, point(hour).at, 100, 110, 90, 100 + hour)
        streams = {"H1": [bar("H1", 1), bar("H1", 5)],
                   "H4": [bar("H4", h) for h in (2, 4, 6)], "D1": []}
        points = []
        def run():
            for p in MultiTimeframeReplay(streams, Engine(), on_observation=self.repo.observe).run():
                points.append(p)
                yield p
        self.repo.append_points(run(), batch_size=1)
        self.repo.finish_run()
        self.assertEqual(len(self.repo.events.docs), 5)
        self.assertEqual(self.repo.runs.docs["sample"]["committed_event_seq"], 4)
        for p in points:
            self.assertEqual(self.reader().reconstruct(p.at, from_events=True)["timeframes"], p.zones)
        self.assertEqual(self.reader().reconstruct(point(5).at, from_events=True)["timeframes"]["H4"]["zones"][0]["effective_energy"], 104)

    def test_observer_with_actual_v1_engine_preserves_outputs(self):
        from test_v1_adapter import Boundary, v1_candles
        from market_streams import completed_bars
        from v1_adapter import V1ZoneEngineAdapter
        def replay(observer=None):
            streams = {"H1": completed_bars("H1", v1_candles(),
                start=datetime(2025, 1, 1, tzinfo=timezone.utc),
                end=datetime(2025, 1, 2, tzinfo=timezone.utc)), "H4": [], "D1": []}
            adapter = V1ZoneEngineAdapter(lambda tf, config: Boundary(),
                {"H1": 5933, "H4": 1601, "D1": 313})
            return MultiTimeframeReplay(streams, adapter, on_observation=observer).run()
        expected = list(replay())
        self.repo.append_points(replay(self.repo.observe), batch_size=3)
        self.repo.finish_run()
        for p in expected:
            self.assertEqual(self.reader().reconstruct(p.at, from_events=True)["timeframes"], p.zones)

    def test_large_replay_gate_rejects_missing_or_changed_configuration(self):
        with self.assertRaises(ValueError):
            require_validated_smoke(self.repo, None, {})
        self.repo.append_points(self.points([point()]))
        self.repo.finish_run()
        with self.assertRaises(ValueError):
            require_validated_smoke(self.repo, "sample", {"H1": 1, "H4": 1, "D1": 1})

    def test_invalid_precision_and_nan_poison_writer(self):
        for case in ("precision", "nan"):
            r = MongoEventRepository(client=self.client)
            self.begin(r, case)
            p = point()
            if case == "precision":
                p.at = p.at.replace(microsecond=1)
            else:
                p.zones["H1"]["zones"][0]["effective_energy"] = float("nan")
            with self.assertRaises(ValueError):
                r.observe("H1", p.at, p.zones["H1"])
            with self.assertRaises(RuntimeError):
                r.finish_run()

    def test_zone_reordering_and_count_decrease_preserved(self):
        a, b = point(1, 5), point(2, 5)
        second = deepcopy(a.zones["H1"]["zones"][0])
        second.update(zone_id="H1:2", local_zone_id=2)
        a.zones["H1"]["zones"].append(second)
        first = deepcopy(b.zones["H1"]["zones"][0])
        first["interaction_count"] = 0
        b.zones["H1"]["zones"] = [deepcopy(second), first]
        self.repo.append_points(self.points([a, b]))
        self.repo.finish_run()
        self.assertEqual(self.reader().reconstruct(b.at, from_events=True)["timeframes"], b.zones)


if __name__ == "__main__":
    unittest.main()
