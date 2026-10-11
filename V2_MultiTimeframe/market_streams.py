"""Convert V1 Mongo start-stamped candles into causally completed V2 bars.

The imported HistData timestamp must be a naive UTC start stamp. Validate
source timezone and broker/session convention before historical evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from multi_timeframe_replay import ClosedBar, TIMEFRAMES
from v1_adapter import DURATION


def completed_bars(timeframe: str, candles: Iterable, *, start: datetime,
                   end: datetime) -> Iterator[ClosedBar]:
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    if (start.tzinfo is None or start.utcoffset() is None or
            end.tzinfo is None or end.utcoffset() is None):
        raise ValueError("start/end require timezone-aware datetimes")
    if start >= end:
        raise ValueError("start must precede end")
    for candle in candles:
        if candle.datetime.tzinfo is not None:
            raise ValueError("V1 candle.datetime must be a naive UTC start stamp")
        opened_at = candle.datetime.replace(tzinfo=timezone.utc)
        closed_at = opened_at + DURATION[timeframe]
        if closed_at < start:
            continue
        if closed_at > end:
            # Do not admit incomplete bars beyond the requested horizon.
            break
        yield ClosedBar(timeframe, closed_at, candle.open, candle.high,
                        candle.low, candle.close, volume=candle.volume)
