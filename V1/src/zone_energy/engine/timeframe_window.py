from datetime import datetime, timedelta

from zone_energy.config import EngineTimeframe


class TimeframeWindow:
    """
    Calculates the time window of a main-timeframe candle.

    The returned interval is:
        [start, end)

    Supported V1 timeframes:
        H1
        H4
        D1
    """

    _DURATIONS = {
        EngineTimeframe.H1: timedelta(hours=1),
        EngineTimeframe.H4: timedelta(hours=4),
        EngineTimeframe.D1: timedelta(days=1),
    }

    @classmethod
    def get(
        cls,
        candle_datetime: datetime,
        timeframe: EngineTimeframe,
    ) -> tuple[datetime, datetime]:

        try:
            duration = cls._DURATIONS[timeframe]
        except KeyError:
            raise ValueError(
                f"Unsupported engine timeframe: {timeframe}"
            ) from None

        start = candle_datetime
        end = start + duration

        return start, end