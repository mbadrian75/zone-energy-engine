from __future__ import annotations

from typing import TYPE_CHECKING

from zone_energy.config import EngineConfig
from zone_energy.engine.timeframe_window import TimeframeWindow
from zone_energy.engine.zone_boundary_detector import ZoneBoundaryDetector
from zone_energy.models import Candle, Reversal

if TYPE_CHECKING:
    from zone_energy.data import MarketDataRepository


class ZoneBoundaryService:
    """
    Resolves zone boundaries from real M15 market data.

    Flow:
        Main-timeframe C2
        -> C2 time window
        -> M15 candles inside C2
        -> oldest M15 candle that created the extreme
        -> zone lower/upper boundary
    """

    def __init__(
        self,
        repository: MarketDataRepository,
        config: EngineConfig,
    ) -> None:
        self._repository = repository
        self._config = config
        self._detector = ZoneBoundaryDetector(config)

    def resolve(
        self,
        reversal: Reversal,
        origin_candle: Candle,
    ) -> tuple[float, float] | None:

        start, end = TimeframeWindow.get(
            candle_datetime=origin_candle.datetime,
            timeframe=self._config.timeframe,
        )

        m15_candles = self._repository.get_candles(
            timeframe="M15",
            start=start,
            end=end,
        )

        return self._detector.detect(
            reversal=reversal,
            m15_candles=m15_candles,
        )
