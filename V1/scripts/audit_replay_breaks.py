"""Reconstruct a checkpoint in memory and explain unattributed breaks (read only)."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from zone_energy.models import ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


def inspect(engine, pending, index, candle):
    current = engine._current(pending)
    rows = []
    for event in pending.unattributed_breaks[len(engine.state.unattributed_breaks):]:
        if current is None:
            reason = "no_open_interaction"
        elif current[0].id == event["zone_id"]:
            reason = "origin_zone_itself_broken"
        elif not ((current[0].type == ZoneType.SUPPORT and candle.is_bullish)
                  or (current[0].type == ZoneType.RESISTANCE and candle.is_bearish)):
            reason = "candle_direction_not_aligned_with_origin"
        else:
            reason = "eligible_origin_but_break_not_attributed"
        rows.append({**event, "datetime": candle.datetime.isoformat(),
                     "diagnosis": reason, "origin_zone_id": current[0].id if current else None,
                     "interaction_id": current[1].id if current else None,
                     "origin_type": current[0].type.value if current else None,
                     "open": candle.open, "high": candle.high, "low": candle.low})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--database", default="market_data")
    args = parser.parse_args()
    from zone_energy.data import EngineResultsRepository, MarketDataRepository
    uri = os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/")
    market = MarketDataRepository(uri, args.database)
    results = EngineResultsRepository(uri, args.database)
    try:
        identifier = json.dumps([args.run_id, "XAUUSD", args.timeframe, args.index], separators=(",", ":"))
        document = results.get_checkpoint(identifier)
        if document is None:
            raise ValueError("Checkpoint not found")
        context = document["replay_context"]
        values = dict(document["config"])
        values["timeframe"] = EngineTimeframe(values["timeframe"])
        config = EngineConfig(**values)
        engine = ReplayEngine(config, document["year_candles"], ZoneBoundaryService(market, config))
        rows = []
        for candle in market.stream_candles(args.timeframe, context["start"], context["end"]):
            engine.process(candle, before_commit=lambda pending, index, bar:
                           rows.extend(inspect(engine, pending, index, bar)))
            if engine.current_index == args.index:
                break
        if (engine.current_index != args.index
                or engine.state.zones != results.load_zones(identifier)
                or engine.state.unattributed_breaks != context["unattributed_breaks"]
                or engine._last_datetime != context["candle_datetime"]):
            raise ValueError("Reconstructed history differs from checkpoint; report withheld")
        print("Checkpoint reconstruction: MATCH")
        print(f"Unattributed breaks: {len(rows)}")
        for row in rows:
            print(json.dumps(row, ensure_ascii=False))
    finally:
        results.close()
        market.close()


if __name__ == "__main__":
    main()
