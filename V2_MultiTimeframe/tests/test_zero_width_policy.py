from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.models import Candle
from zone_energy.replay.replay_engine import ReplayEngine
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from zero_distance_policy import V2ReplayEngine
from mongo_event_repository import MongoEventRepository, MongoEventReader, apply_event
from multi_timeframe_replay import MultiTimeframeReplay, ClosedBar
from v1_adapter import V1ZoneEngineAdapter
from test_mongo_event_repository import client
from validate_event_run import validate

COUNTS = {"H1": 5933, "H4": 1601, "D1": 313}
START = datetime(2012, 4, 6, tzinfo=timezone.utc)


class M15:
    def __init__(self, lower=1640.1):
        self.lower = lower
    def get_candles(self, timeframe, start, end):
        # Exact flat M15 candle reported by the user's server.
        return [Candle(datetime(2012, 4, 6, 11, 45), 1640.1,
                       1640.1, self.lower, 1640.1, 0.0)]


def candles():
    return [Candle(datetime(2012, 4, 6, hour), *prices, 0.0) for hour, prices in (
        (10, (1639.5, 1639.9, 1639.0, 1639.7)),
        (11, (1640.1, 1640.1, 1640.1, 1640.1)),
        (12, (1639.8, 1640.0, 1639.6, 1639.7)))]


def engine(engine_type=V2ReplayEngine, lower=1640.1):
    config = EngineConfig(timeframe=EngineTimeframe.H1)
    result = engine_type(config, 5933, ZoneBoundaryService(M15(lower), config))
    result.state.next_zone_id = 915
    for candle in candles()[:2]:
        result.process(candle)
    return result


def audited_replay(repo):
    adapter = V1ZoneEngineAdapter(lambda tf, cfg: ZoneBoundaryService(M15(), cfg), COUNTS)
    bars = [ClosedBar("H1", c.datetime.replace(tzinfo=timezone.utc) + timedelta(hours=1),
                      c.open, c.high, c.low, c.close, volume=c.volume) for c in candles()]
    streams = {"H1": bars, "H4": [], "D1": []}
    replay = MultiTimeframeReplay(streams, adapter,
        on_observation=lambda tf, at, state: repo.observe(
            tf, at, state, rejections=adapter.recent_rejections(tf)))
    repo.append_points(replay.run(), batch_size=1)
    repo.finish_run()
    return bars


class ZeroWidthPolicyTests(unittest.TestCase):
    def test_real_flat_m15_reproduces_v1_failure_and_v2_continues(self):
        original = engine(ReplayEngine)
        with self.assertRaisesRegex(ValueError, "Invalid zone 915"):
            original.process(candles()[2])
        guarded = engine()
        events = guarded.process(candles()[2])
        self.assertIn("zero_width_zone_rejected", events)
        self.assertNotIn("zone_created", events)
        self.assertEqual(guarded.state.zones, [])
        self.assertEqual(guarded.state.next_zone_id, 915)
        self.assertEqual(guarded.state.next_interaction_id, 1)
        self.assertEqual(guarded.current_index, 2)
        audit = guarded.recent_policy_rejections[0]
        self.assertEqual(audit["reason"], "zero_width_boundary")
        self.assertEqual((audit["lower_price"], audit["upper_price"]), (1640.1, 1640.1))
        guarded.process(Candle(datetime(2012, 4, 6, 13), 1639.7, 1639.8, 1639.6, 1639.7, 0))
        self.assertEqual(guarded.recent_policy_rejections, [])

    def test_positive_boundary_matches_v1(self):
        a, b = engine(ReplayEngine, 1639.9), engine(V2ReplayEngine, 1639.9)
        self.assertEqual(a.process(candles()[2]), b.process(candles()[2]))
        self.assertEqual(a.state, b.state)
        self.assertEqual(len(b.state.zones), 1)

    def test_failed_commit_does_not_leak_audit(self):
        guarded = engine()
        before = deepcopy(guarded.state)
        def fail(*args):
            raise OSError("failed commit")
        with self.assertRaises(OSError):
            guarded.process(candles()[2], before_commit=fail)
        self.assertEqual(guarded.state, before)
        self.assertEqual(guarded.current_index, 1)
        self.assertEqual(guarded.recent_policy_rejections, [])
        guarded.process(candles()[2])
        self.assertEqual(len(guarded.recent_policy_rejections), 1)

    def test_other_invalid_boundaries_are_not_suppressed(self):
        guarded = engine(lower=1640.2)
        with self.assertRaisesRegex(ValueError, "Invalid candle"):
            guarded.process(candles()[2])
        self.assertEqual(guarded.current_index, 1)

    def test_zero_width_rejection_preserves_open_interaction(self):
        from test_zero_distance_policy import seeded, report_candles
        from types import SimpleNamespace
        guarded = seeded()
        guarded.state.zones = [guarded.state.zones[1]]
        before = deepcopy(guarded.state.zones[0].interactions)
        guarded.boundary_service = SimpleNamespace(resolve=lambda *args: (1360.43, 1360.43))
        events = guarded.process(report_candles()[2])
        self.assertIn("zero_width_zone_rejected", events)
        self.assertEqual(guarded.state.zones[0].interactions, before)
        self.assertEqual(len(guarded.state.zones), 1)
        self.assertEqual(guarded.state.next_zone_id, 425)

    def test_audit_reconstruction_validation_and_corruption(self):
        repo = MongoEventRepository(client=client(), event_batch_size=1)
        repo.begin_run(run_id="flat", start=START, end=START + timedelta(days=1), year_candles=COUNTS)
        bars = audited_replay(repo)
        reader = MongoEventReader(repo, "flat")
        with TemporaryDirectory() as directory:
            reference = Path(directory) / "reference.jsonl"
            with reference.open("x", encoding="utf-8") as output:
                for bar in bars:
                    body = reader.reconstruct(bar.closed_at)
                    self.assertEqual(body, reader.reconstruct(bar.closed_at, from_events=True))
                    output.write(json.dumps(body) + "\n")
            report = validate(repo, "flat", reference)
            self.assertEqual(report["zero_width_boundary_rejections"], 1)
        audit = next(iter(repo.events.docs.values()))
        self.assertEqual(audit["kind"], "boundary_rejected")
        self.assertIsNone(audit["zone_id"])
        corrupt = deepcopy(audit)
        corrupt["reaction"]["upper_price"] += 1
        with self.assertRaisesRegex(ValueError, "boundary rejection"):
            apply_event({}, corrupt)
        corrupt = deepcopy(audit)
        corrupt["reaction"]["rejected_at"] += 1
        with self.assertRaises(ValueError):
            apply_event({}, corrupt)

    def test_historical_committed_audits_are_reported_once(self):
        guarded = engine()
        def revision(state, index, candle):
            record = deepcopy(state.rejected_reactions[-1])
            record.update(reaction_index=0, detection_index=1, rejected_at=1,
                          origin_datetime="2012-04-06T09:00:00",
                          rejected_datetime="2012-04-06T10:00:00")
            state.rejected_reactions.append(record)
        guarded.process(candles()[2], before_commit=revision)
        self.assertEqual(len(guarded.recent_policy_rejections), 2)
        guarded.process(Candle(datetime(2012, 4, 6, 13), 1639.7, 1639.8, 1639.6, 1639.7, 0))
        self.assertEqual(guarded.recent_policy_rejections, [])
