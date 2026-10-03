"""Reconstruct a checkpoint in memory and explain unattributed breaks (read only)."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.models import ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


def inspect(engine, pending, index, candle):
    current = engine._current(pending)
    rows = []
    previous_keys = {(event["zone_id"], event["candle_index"]) for event in engine.state.unattributed_breaks}
    for event in pending.unattributed_breaks:
        if (event["zone_id"], event["candle_index"]) in previous_keys:
            continue
        if event["candle_index"] != index:
            rows.append({**event, "diagnosis": "historical_event_recomputed_after_invalidation"})
            continue
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
    parser.add_argument("--check-c3", action="store_true",
                        help="Compare each break candle with the next C3 confirmation, read only")
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
        rows = {}
        candles = []
        def collect(pending, index, bar):
            retained = {(event["zone_id"], event["candle_index"]) for event in pending.unattributed_breaks}
            for key in list(rows):
                if key not in retained:
                    del rows[key]
            for row in inspect(engine, pending, index, bar):
                rows[(row["zone_id"], row["candle_index"])] = row
        for candle in market.stream_candles(args.timeframe, context["start"], context["end"]):
            engine.process(candle, before_commit=collect)
            candles.append(candle)
            if engine.current_index == args.index:
                break
        if (engine.current_index != args.index
                or engine.state.zones != results.load_zones(identifier)
                or engine.state.unattributed_breaks != context["unattributed_breaks"]
                or engine.state.invalidated_reactions != context.get("invalidated_reactions", [])
                or engine.state.pending_c2_breaks != context.get("pending_c2_breaks", [])
                or engine.state.confirmed_c2_breaks != context.get("confirmed_c2_breaks", [])
                or engine._last_datetime != context["candle_datetime"]):
            raise ValueError("Reconstructed history differs from checkpoint; report withheld")
        print("Checkpoint reconstruction: MATCH")
        print(f"Unattributed breaks: {len(rows)}")
        confirmation_counts = {}
        for row in sorted(rows.values(), key=lambda row: (row["candle_index"], row["zone_id"])):
            if args.check_c3:
                row = compare_c3(row, candles, engine.state)
                category = row["c3_check"]
                confirmation_counts[category] = confirmation_counts.get(category, 0) + 1
            print(json.dumps(row, ensure_ascii=False))
        if args.check_c3:
            print("C3 summary (counts are break events, not unique candles):")
            print(json.dumps(confirmation_counts, ensure_ascii=False))
        print(f"Invalidated reactions: {len(engine.state.invalidated_reactions)}")
        for reaction in engine.state.invalidated_reactions:
            report = {key: value for key, value in reaction.items() if key != "invalid_interaction"}
            print(json.dumps(report, ensure_ascii=False, default=str))
        print(f"Confirmed outgoing C2 breaks: {len(engine.state.confirmed_c2_breaks)}")
        for report in engine.state.confirmed_c2_breaks:
            print(json.dumps(report, ensure_ascii=False))
    finally:
        results.close()
        market.close()


def compare_c3(row, candles, state):
    """Retrospective diagnosis only; never assign energy using future data."""
    result = dict(row)
    index = row["candle_index"]
    if index < 1 or index + 1 >= len(candles):
        result["c3_check"] = "three_candle_window_unavailable"
        return result
    origin = row.get("origin_type")
    if origin is None:
        result["c3_check"] = "historical_origin_context_unavailable"
        return result
    previous_type = ZoneType(origin)
    reversal = ReversalDetector.detect(
        candles[index-1], candles[index], candles[index+1], index-1, index, index+1,
        previous_type=previous_type,
    )
    result["c3_index"] = index + 1
    result["c3_datetime"] = candles[index+1].datetime.isoformat()
    result["next_confirmed_pattern"] = reversal.type.value if reversal else None
    if reversal is None or reversal.type == previous_type:
        result["c3_check"] = "no_opposite_pattern_on_break_candle"
        return result
    accepted = []
    for zone in state.zones:
        for interaction in zone.interactions:
            if (interaction.start_index == index
                    and interaction.start_price == reversal.extreme_price):
                accepted.append({"zone_id":zone.id, "interaction_id":interaction.id})
    invalid = [{"zone_id":reaction["zone_id"], "interaction_id":reaction["interaction_id"],
                "invalidated_at":reaction["break_index"]}
               for reaction in state.invalidated_reactions
               if reaction["reaction_index"] == index
               and reaction["reaction_type"] == reversal.type.value]
    result["valid_reactions_at_c2"] = accepted
    result["later_invalidated_reactions_at_c2"] = invalid
    result["c3_check"] = (
        "opposite_reaction_confirmed_next_candle" if accepted else
        "opposite_reaction_later_invalidated" if invalid else
        "opposite_pattern_without_retained_reaction"
    )
    return result


if __name__ == "__main__":
    main()
