"""Connect unchanged V1 engines to V2 causal H1/H4/D1 replay.

HistData Mongo candles have START-stamped naive timestamps. This adapter
receives completed UTC bars and restores their original V1 opening timestamps.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import Callable

from multi_timeframe_replay import ClosedBar, TIMEFRAMES
from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.models import Candle
from zone_energy.replay.replay_engine import ReplayEngine

DURATION = {"H1": timedelta(hours=1), "H4": timedelta(hours=4), "D1": timedelta(days=1)}


class V1ZoneEngineAdapter:
    """Three independent V1 engines, with timeframe-scoped IDs and energies.

    boundary_service_factory(tf, config) returns a V1-compatible service.
    For real data use ZoneBoundaryService(market_repository, config), which
    resolves M15 boundaries of a previously completed C2 candle.
    year_candles must be an a-priori configuration, not future market data.
    """

    def __init__(
        self,
        boundary_service_factory: Callable[[str, EngineConfig], object],
        year_candles: dict[str, int],
    ) -> None:
        if set(year_candles) != set(TIMEFRAMES):
            raise ValueError("year_candles requires exactly H1, H4 and D1")
        self.engines: dict[str, ReplayEngine] = {}
        self.energy: dict[str, EffectiveZoneEnergyCalculator] = {}
        self.market_energy: dict[str, MarketEnergySnapshotCalculator] = {}
        for timeframe in TIMEFRAMES:
            count = year_candles[timeframe]
            if type(count) is not int or count <= 0:
                raise ValueError(f"Invalid year_candles for {timeframe}")
            config = EngineConfig(timeframe=EngineTimeframe(timeframe))
            self.engines[timeframe] = ReplayEngine(
                config, count, boundary_service_factory(timeframe, config)
            )
            self.energy[timeframe] = EffectiveZoneEnergyCalculator(config)
            self.market_energy[timeframe] = MarketEnergySnapshotCalculator(config)
        self._last_closed = {tf: None for tf in TIMEFRAMES}

    def on_closed_bar(self, timeframe: str, bar: ClosedBar) -> None:
        if timeframe not in self.engines or bar.timeframe != timeframe:
            raise ValueError("Timeframe mismatch")
        close_utc = bar.closed_at.astimezone(timezone.utc)
        opened_utc = close_utc - DURATION[timeframe]
        if self._last_closed[timeframe] is not None and close_utc <= self._last_closed[timeframe]:
            raise ValueError(f"Non-increasing close times for {timeframe}")
        # V1/Mongo M15 windows use naive start timestamps.
        candle = Candle(opened_utc.replace(tzinfo=None), bar.open, bar.high,
                        bar.low, bar.close, bar.volume)
        self.engines[timeframe].process(candle)
        self._last_closed[timeframe] = close_utc

    def snapshot(self, timeframe: str) -> dict:
        if timeframe not in self.engines:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        engine = self.engines[timeframe]
        index = engine.current_index
        if index == -1:
            return {"candle_index": None, "median_active_energy": None, "zones": []}
        reference = self.market_energy[timeframe].capture(
            engine.state.zones, index, engine.year_candles
        )
        zones = []
        for zone in engine.state.zones:
            zones.append({
                "zone_id": f"{timeframe}:{zone.id}",
                "local_zone_id": zone.id,
                "type": zone.type.value,
                "state": zone.state.value,
                "lower_price": zone.lower_price,
                "upper_price": zone.upper_price,
                "creation_index": zone.creation_index,
                "created_at_index": zone.created_at_index,
                "interaction_count": len(zone.interactions),
                "effective_energy": self.energy[timeframe].calculate(
                    zone, index, engine.year_candles
                ),
            })
        return {"candle_index": index,
                "median_active_energy": reference.median_active_energy,
                "zones": zones}
