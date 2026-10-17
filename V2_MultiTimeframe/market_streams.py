"""Convert V1 Mongo start-stamped candles into causally completed V2 bars.

The imported HistData timestamp must be a naive UTC start stamp. Validate
source timezone and broker/session convention before historical evaluation.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Iterator

from multi_timeframe_replay import ClosedBar, TIMEFRAMES
from v1_adapter import DURATION


def paged_candles(market, timeframe, start, end, *, page_size=1000):
    """Read immutable market history without holding cursors during replay.

    Fetch one extra row to detect duplicate timestamps at page boundaries.
    Every cursor is exhausted and closed before any candle reaches the engine.
    Source collections must remain unchanged throughout a replay.
    """
    if start >= end or page_size <= 0:
        raise ValueError("Invalid market page interval or size")
    collection = market._get_collection(timeframe)
    previous = None
    while True:
        bounds = {"$gte": start, "$lt": end} if previous is None else {
            "$gt": previous, "$lt": end}
        cursor = collection.find({"datetime": bounds}).sort("datetime", 1).limit(page_size + 1)
        try:
            documents = list(cursor)
        finally:
            cursor.close()
        last = previous
        for document in documents:
            stamp = document["datetime"]
            if not start <= stamp < end or (last is not None and stamp <= last):
                raise ValueError("Market timestamps must be unique and strictly increasing")
            last = stamp
        page = documents[:page_size]
        for document in page:
            yield market._document_to_candle(document)
        if len(documents) <= page_size:
            return
        previous = page[-1]["datetime"]


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
