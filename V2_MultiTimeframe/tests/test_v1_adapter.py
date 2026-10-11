"""Integration checks against the unchanged Zone Energy V1 engine."""
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "V1" / "src"))
sys.path.insert(0, str(BASE / "V2_MultiTimeframe"))

from multi_timeframe_replay import MultiTimeframeReplay
from market_streams import completed_bars
from v1_adapter import V1ZoneEngineAdapter
from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.models import Candle
from zone_energy.replay.replay_engine import ReplayEngine

UTC = timezone.utc


class Boundary:
    def resolve(self, reversal, origin):
        if reversal.type.value == "support":
            return origin.low, min(origin.low + 5, origin.high)
        return max(origin.high - 10, origin.low), origin.high


def v1_candles():
    start = datetime(2025, 1, 1)
    prices = [(110, 112, 105, 108), (108, 110, 100, 102),
              (102, 111, 102, 109), (109, 130, 108, 125),
              (125, 128, 110, 115), (115, 120, 95, 100),
              (100, 122, 98, 118)]
    return [Candle(start + timedelta(hours=i), *prices[i], 20 + i)
            for i in range(len(prices))]


class V1AdapterTests(unittest.TestCase):
    def factory(self, tf, config):
        return Boundary()

    def make_adapter(self):
        return V1ZoneEngineAdapter(self.factory, {"H1": 1000, "H4": 250, "D1": 100})

    def test_matches_unmodified_v1_zone_history(self):
        rows = v1_candles()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = start + timedelta(hours=8)
        streams = {
            "H1": completed_bars("H1", rows, start=start, end=end),
            "H4": iter(()), "D1": iter(()),
        }
        adapter = self.make_adapter()
        points = list(MultiTimeframeReplay(streams, adapter).run())
        reference = ReplayEngine(
            EngineConfig(timeframe=EngineTimeframe.H1), 1000, Boundary()
        )
        for candle in rows:
            reference.process(candle)
        self.assertEqual(adapter.engines["H1"].state, reference.state)
        self.assertEqual(len(points), len(rows))
        self.assertEqual(points[0].at, start + timedelta(hours=1))
        self.assertEqual(points[-1].zones["H1"]["candle_index"], 6)
        self.assertEqual(points[-1].zones["H4"]["zones"], [])
        self.assertTrue(all(
            z["zone_id"].startswith("H1:")
            for z in points[-1].zones["H1"]["zones"]
        ))

    def test_future_bars_do_not_change_prefix_snapshots(self):
        rows = v1_candles()
        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = start + timedelta(hours=8)

        def run(subset):
            streams = {"H1": completed_bars("H1", subset, start=start, end=end),
                       "H4": iter(()), "D1": iter(())}
            return list(MultiTimeframeReplay(streams, self.make_adapter()).run())

        self.assertEqual(run(rows)[:4], run(rows[:4]))

    def test_partial_higher_timeframe_not_loaded(self):
        start = datetime(2025, 1, 1, tzinfo=UTC)
        h1 = [Candle(datetime(2025,1,1,h), 100,102,99,101,1)
              for h in range(4)]
        h4 = [Candle(datetime(2025,1,1),100,102,99,101,1)]
        streams = {
            "H1": completed_bars("H1",h1,start=start,end=start+timedelta(hours=4)),
            "H4": completed_bars("H4",h4,start=start,end=start+timedelta(hours=4)),
            "D1": iter(()),
        }
        points = list(MultiTimeframeReplay(streams, self.make_adapter()).run())
        self.assertIsNone(points[2].zones["H4"]["candle_index"])
        self.assertEqual(points[3].zones["H4"]["candle_index"],0)

    def test_undefined_energy_remains_none(self):
        rows = v1_candles()[:3]
        adapter = self.make_adapter()
        start = datetime(2025,1,1,tzinfo=UTC)
        for bar in completed_bars("H1", rows, start=start,
                                  end=start+timedelta(days=1)):
            adapter.on_closed_bar("H1", bar)
        snapshot = adapter.snapshot("H1")
        self.assertEqual(len(snapshot["zones"]), 1)
        self.assertIsNone(snapshot["zones"][0]["effective_energy"])

    def test_stream_rejects_aware_source_start_stamp(self):
        row = Candle(datetime(2025,1,1,tzinfo=UTC),100,102,99,101,0)
        with self.assertRaisesRegex(ValueError, "naive UTC"):
            list(completed_bars("H1", [row],
                start=datetime(2025,1,1,tzinfo=UTC),
                end=datetime(2025,1,2,tzinfo=UTC)))


if __name__ == "__main__":
    unittest.main()
