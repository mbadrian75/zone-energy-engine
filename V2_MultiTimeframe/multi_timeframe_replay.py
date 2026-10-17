"""Causal, completed-candle multi-timeframe replay for XAUUSD.

Contract: the supplied engine must calculate/update zone state *only* when it
receives on_closed_bar(); snapshot() must expose no future-derived features.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from heapq import heappop, heappush
from typing import Any, Iterable, Iterator, Mapping, Protocol

TIMEFRAMES = ("H1", "H4", "D1")
# At identical close times, higher timeframes are processed before H1 decisions.
_PRIORITY = {"D1": 0, "H4": 1, "H1": 2}


@dataclass(frozen=True)
class ClosedBar:
    timeframe: str
    closed_at: datetime  # timezone-aware; time is when close is actually known
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def __post_init__(self) -> None:
        if self.timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")
        if self.closed_at.tzinfo is None or self.closed_at.utcoffset() is None:
            raise ValueError("closed_at must be timezone-aware")
        if not all(isfinite(x) for x in (self.open, self.high, self.low, self.close, self.volume)):
            raise ValueError("OHLCV must be finite")
        if self.volume < 0:
            raise ValueError("Volume cannot be negative")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("Invalid OHLC")


class ZoneEngineAdapter(Protocol):
    def on_closed_bar(self, timeframe: str, bar: ClosedBar) -> None: ...
    def snapshot(self, timeframe: str) -> Any: ...


@dataclass(frozen=True)
class DecisionPoint:
    at: datetime
    zones: Mapping[str, Any]
    last_closed_at: Mapping[str, datetime | None]


class MultiTimeframeReplay:
    """Generate decisions at every H1 close with H1/H4/D1 causal state.

    `streams` must contain per-timeframe chronological CLOSED bars. A bar must
    not become available before its closed_at instant. The adapter must not
    compute zone scores using data that were unavailable at on_closed_bar time.
    """

    def __init__(self, streams: Mapping[str, Iterable[ClosedBar]], engine: ZoneEngineAdapter,
                 *, on_observation=None):
        if set(streams) != set(TIMEFRAMES):
            raise ValueError("Expected exactly H1, H4, D1 streams")
        self.streams = streams
        self.engine = engine
        self.on_observation = on_observation

    def run(self) -> Iterator[DecisionPoint]:
        iterators = {tf: iter(self.streams[tf]) for tf in TIMEFRAMES}
        previous: dict[str, datetime] = {}
        heap: list[tuple[datetime, int, str, ClosedBar]] = []
        last_seen: dict[str, datetime | None] = {tf: None for tf in TIMEFRAMES}

        def push_next(tf: str) -> None:
            bar = next(iterators[tf], None)
            if bar is None:
                return
            if bar.timeframe != tf:
                raise ValueError(f"Unexpected bar timeframe in {tf} stream")
            if tf in previous and bar.closed_at <= previous[tf]:
                raise ValueError(f"Non-increasing closed_at values in {tf} stream")
            previous[tf] = bar.closed_at
            heappush(heap, (bar.closed_at, _PRIORITY[tf], tf, bar))

        for tf in TIMEFRAMES:
            push_next(tf)

        while heap:
            instant, _, tf, bar = heappop(heap)
            self.engine.on_closed_bar(tf, bar)
            last_seen[tf] = instant
            if self.on_observation is not None:
                self.on_observation(tf, instant, deepcopy(self.engine.snapshot(tf)))
            # Feed the next candle only after the current one is consumed.
            push_next(tf)
            if tf == "H1":
                zones = {name: deepcopy(self.engine.snapshot(name)) for name in TIMEFRAMES}
                yield DecisionPoint(instant, zones, dict(last_seen))
