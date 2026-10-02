from collections.abc import Iterable

from zone_energy.config import EngineConfig
from zone_energy.models import Candle, Reversal, ZoneType


class ZoneBoundaryDetector:
    """
    Detects zone boundaries from M15 candles.

    V1 rule:
    - Support: find the oldest M15 candle whose low matches
      the reversal extreme.
    - Resistance: find the oldest M15 candle whose high matches
      the reversal extreme.
    - The full range of that M15 candle becomes the zone boundary.
    """

    def __init__(self, config: EngineConfig) -> None:
        self._config = config

    def detect(
        self,
        reversal: Reversal,
        m15_candles: Iterable[Candle],
    ) -> tuple[float, float] | None:

        tolerance = self._config.extreme_price_tolerance

        # Sort explicitly so the oldest matching M15 candle
        # is always selected.
        candles = sorted(
            m15_candles,
            key=lambda candle: candle.datetime,
        )

        for candle in candles:

            if reversal.type == ZoneType.SUPPORT:
                difference = abs(
                    candle.low - reversal.extreme_price
                )

            elif reversal.type == ZoneType.RESISTANCE:
                difference = abs(
                    candle.high - reversal.extreme_price
                )

            else:
                raise ValueError(
                    f"Unsupported reversal type: {reversal.type}"
                )

            if difference <= tolerance:
                return (
                    candle.low,
                    candle.high,
                )

        return None