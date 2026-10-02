import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from zone_energy.models import Candle, Reversal, ZoneType


class MemoryRepository:
    def __init__(self, candles):
        self.candles = candles
        self.requests = []

    def get_candles(self, timeframe, start, end):
        self.requests.append((timeframe, start, end))
        return [candle for candle in self.candles if start <= candle.datetime < end]


class LocalBoundaryServiceTests(unittest.TestCase):
    def test_timeframe_window_and_oldest_matching_candle(self):
        start = datetime(2025, 1, 1, 0)
        for timeframe, hours in ((EngineTimeframe.H1, 1), (EngineTimeframe.H4, 4), (EngineTimeframe.D1, 24)):
            for kind, extreme in ((ZoneType.SUPPORT, 100), (ZoneType.RESISTANCE, 110)):
                with self.subTest(timeframe=timeframe, kind=kind):
                    oldest_low = 100 if kind == ZoneType.SUPPORT else 101
                    oldest_high = 109 if kind == ZoneType.SUPPORT else 110
                    candles = [
                        Candle(start + timedelta(minutes=30), 103, 110, 100, 105, 0),
                        Candle(start + timedelta(minutes=15), 104, oldest_high, oldest_low, 106, 0),
                        Candle(start - timedelta(minutes=15), 101, 115, 95, 102, 0),
                        Candle(start + timedelta(hours=hours), 101, 115, 95, 102, 0),
                    ]
                    repository = MemoryRepository(candles)
                    service = ZoneBoundaryService(repository, EngineConfig(timeframe=timeframe))
                    origin = Candle(start, 104, 110, 100, 105, 0)
                    reversal = Reversal(kind, extreme, 10, 11)
                    self.assertEqual(service.resolve(reversal, origin), (oldest_low, oldest_high))
                    self.assertEqual(repository.requests, [("M15", start, start + timedelta(hours=hours))])

    def test_missing_matching_extreme_returns_none(self):
        start = datetime(2025, 1, 1)
        repository = MemoryRepository([Candle(start, 104, 110, 100, 105, 0)])
        service = ZoneBoundaryService(repository, EngineConfig())
        origin = Candle(start, 104, 110, 100, 105, 0)
        self.assertIsNone(service.resolve(Reversal(ZoneType.SUPPORT, 95, 10, 11), origin))

    def test_empty_repository_returns_none(self):
        origin = Candle(datetime(2025, 1, 1), 104, 110, 100, 105, 0)
        service = ZoneBoundaryService(MemoryRepository([]), EngineConfig())
        self.assertIsNone(service.resolve(Reversal(ZoneType.SUPPORT, 100, 10, 11), origin))


if __name__ == "__main__":
    unittest.main()
