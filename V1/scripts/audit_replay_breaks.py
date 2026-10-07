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
from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
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
        else:
            reason = "eligible_origin_but_break_not_attributed"
        rows.append({**event, "datetime": candle.datetime.isoformat(),
                     "diagnosis": reason, "origin_zone_id": current[0].id if current else None,
                     "interaction_id": current[1].id if current else None,
                     "origin_type": current[0].type.value if current else None,
                     "open": candle.open, "high": candle.high, "low": candle.low})
    return rows


def pending_reaction_report(state, index, last_candle):
    candidate = state.pending_reaction
    if candidate is None:
        return None
    zone = next(zone for zone in state.zones if zone.id == candidate["zone_id"])
    reversal = candidate["reversal"]
    support = reversal["type"] == ZoneType.SUPPORT
    opened = [(item.id,move.id,move.start_index) for item in state.zones for move in item.interactions
              if move.state.value == "open"]
    return {"zone_id":zone.id,"zone_state":zone.state.value,
            "reaction_type":reversal["type"],"reaction_index":reversal["extreme_index"],
            "reaction_datetime":candidate["c2"]["datetime"],
            "reaction_extreme":reversal["extreme_price"],
            "pattern_confirmation_index":reversal["detection_index"],
            "zone_lower":zone.lower_price,"zone_upper":zone.upper_price,
            "confirmation_close_condition":"close > upper" if support else "close < lower",
            "rejection_close_condition":"close < lower" if support else "close > upper",
            "last_index":index,"last_datetime":last_candle.datetime,"last_close":last_candle.close,
            "candles_since_pattern":index-reversal["detection_index"],
            "current_origin_zone_id":opened[0][0] if opened else None,
            "current_interaction_id":opened[0][1] if opened else None,
            "current_origin_index":opened[0][2] if opened else None,
            "status":"waiting_for_close_outside_zone"}


def zone_contacts(state, candle, index):
    """Report contact using roles and states known before processing this candle."""
    rows = []
    for zone in state.zones:
        if zone.created_at_index > index or candle.high < zone.lower_price or candle.low > zone.upper_price:
            continue
        side = ("below" if candle.close < zone.lower_price else
                "above" if candle.close > zone.upper_price else "inside")
        rows.append({"zone_id":zone.id,"type_before_candle":zone.type.value,
            "state_before_candle":zone.state.value,"creation_index":zone.creation_index,
            "lower":zone.lower_price,"upper":zone.upper_price,
            "contains_high":zone.lower_price <= candle.high <= zone.upper_price,
            "contains_low":zone.lower_price <= candle.low <= zone.upper_price,
            "close_side":side,
            "last_external_side_before_candle":(zone.last_external_price_side.value
                if zone.last_external_price_side is not None else None)})
    return {"candle_index":index,"datetime":candle.datetime.isoformat(),
            "open":candle.open,"high":candle.high,"low":candle.low,"close":candle.close,
            "contacted_zones_before_processing":rows}


class EnergySnapshotAudit:
    """Observe actual pre-break snapshots without changing engine inputs or outputs."""
    def __init__(self, delegate, config, zone_id, index, reports):
        self.delegate,self.config = delegate,config
        self.zone_id,self.index,self.reports = zone_id,index,reports

    def capture(self,zones,index,year_candles):
        history = list(zones)
        snapshot = self.delegate.capture(history,index,year_candles)
        if index == self.index and any(key == self.zone_id for key,_ in snapshot.zone_energies):
            zone = next(zone for zone in history if zone.id == self.zone_id)
            decay = InteractionTimeDecayCalculator(self.config)
            interactions = []
            for move in zone.interactions:
                age,weight,_ = decay.calculate(None,move.start_index,index,year_candles)
                closed = move.state.value == "closed"
                contribution = decay.evaluate(move,index,year_candles)[2] if closed else None
                interactions.append({"interaction_id":move.id,"state":move.state.value,
                    "start_index":move.start_index,"end_index":move.end_index,
                    "previous_distance":move.previous_distance,"previous_time":move.previous_movement_time,
                    "distance":move.distance,"movement_time":move.movement_time,
                    "movement_energy":move.movement_energy,"total_break_evidence":move.total_break_evidence,
                    "base_energy":move.base_energy,"age":age,"time_weight":weight,
                    "effective_contribution":contribution,"included_in_sum":closed and contribution is not None,
                    "exclusion_reason":("open_not_finalized" if not closed else
                                         "undefined_finalized_energy" if contribution is None else None)})
            energy,median = snapshot.reference_for_break(self.zone_id)
            self.reports.append({"zone_id":zone.id,"candle_index":index,"state":"active",
                "zone_type":zone.type.value,"creation_index":zone.creation_index,
                "effective_zone_energy":energy,"median_active_energy":median,
                "interactions":interactions,
                "undefined_reason":("no_defined_finalized_contributions" if energy is None else None),
                "zero_reason":("no_finalized_interactions" if energy == 0 and
                                 not any(item["state"] == "closed" for item in interactions) else
                                 "defined_contributions_sum_to_zero" if energy == 0 else None)})
        return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--index", required=True, type=int)
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--check-c3", action="store_true",
                        help="Compare each break candle with the next C3 confirmation, read only")
    parser.add_argument("--inspect-range", type=int, nargs=2, metavar=("FIRST","LAST"),
                        help="Show all zone contacts using historical roles before each candle")
    parser.add_argument("--zone-energy",type=int,help="Inspect a zone's actual pre-break energy snapshot")
    parser.add_argument("--energy-index",type=int,help="Original break index for --zone-energy")
    args = parser.parse_args()
    if args.inspect_range and not 0 <= args.inspect_range[0] <= args.inspect_range[1] <= args.index:
        parser.error("inspect-range must be an ordered range within the checkpoint")
    if (args.zone_energy is None) != (args.energy_index is None):
        parser.error("zone-energy and energy-index must be provided together")
    if args.energy_index is not None and not 0 <= args.energy_index <= args.index:
        parser.error("energy-index must be within the checkpoint")
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
        energy_reports = []
        if args.zone_energy is not None:
            engine._snapshots = EnergySnapshotAudit(engine._snapshots,config,args.zone_energy,args.energy_index,energy_reports)
            engine._breaks._snapshots = EnergySnapshotAudit(engine._breaks._snapshots,config,args.zone_energy,args.energy_index,energy_reports)
        rows = {}
        candles = []
        contacts = []
        def collect(pending, index, bar):
            retained = {(event["zone_id"], event["candle_index"]) for event in pending.unattributed_breaks}
            for key in list(rows):
                if key not in retained:
                    del rows[key]
            for row in inspect(engine, pending, index, bar):
                rows[(row["zone_id"], row["candle_index"])] = row
        for candle in market.stream_candles(args.timeframe, context["start"], context["end"]):
            next_index = engine.current_index+1
            if args.inspect_range and args.inspect_range[0] <= next_index <= args.inspect_range[1]:
                contacts.append(zone_contacts(engine.state,candle,next_index))
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
                  or engine.state.pending_reaction != context.get("pending_reaction")
                  or engine.state.rejected_reactions != context.get("rejected_reactions", [])
                  or engine.state.reaction_confirmations != context.get("reaction_confirmations", [])
                  or engine.state.pending_origin_break != context.get("pending_origin_break")
                  or engine.state.resolved_origin_breaks != context.get("resolved_origin_breaks", [])
                or engine._last_datetime != context["candle_datetime"]):
            raise ValueError("Reconstructed history differs from checkpoint; report withheld")
        print("Checkpoint reconstruction: MATCH")
        if args.zone_energy is not None:
            records = [record for zone in engine.state.zones for move in zone.interactions for record in move.breaks
                       if record.broken_zone_id == args.zone_energy and record.break_index == args.energy_index]
            if len(records) != 1:
                raise ValueError("Selected break record not uniquely found")
            record = records[0]
            matching = [report for report in energy_reports
                        if report["effective_zone_energy"] == record.broken_zone_energy_at_break
                        and report["median_active_energy"] == record.median_active_zone_energy_at_break]
            if not matching:
                raise ValueError("Observed pre-break snapshot differs from stored references")
            print("Zone energy at original break: MATCH")
            print(json.dumps(matching[-1],ensure_ascii=False,default=str))
            print(json.dumps({"break_index":record.break_index,"break_close":record.break_close,
                "stored_energy":record.broken_zone_energy_at_break,"stored_median":record.median_active_zone_energy_at_break,
                "barrier_ratio":record.barrier_ratio,"barrier_cost":record.barrier_cost,
                "break_evidence":record.break_evidence},ensure_ascii=False))
        if args.inspect_range:
            print("Historical zone contacts (observed before each candle; contact alone is not a confirmed reaction):")
            for report in contacts:
                index = report["candle_index"]
                report["retained_reactions"] = [entry for entry in engine.state.reaction_confirmations
                                                 if entry["reaction_index"] == index]
                report["invalidated_reactions"] = [{"zone_id":entry["zone_id"],
                    "reaction_type":entry["reaction_type"],"break_index":entry["break_index"]}
                    for entry in engine.state.invalidated_reactions if entry["reaction_index"] == index]
                print(json.dumps(report, ensure_ascii=False, default=str))
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
        print(f"Rejected reactions: {len(engine.state.rejected_reactions)}")
        for report in engine.state.rejected_reactions:
            print(json.dumps(report, ensure_ascii=False, default=str))
        print(f"Pending reactions: {int(engine.state.pending_reaction is not None)}")
        waiting = pending_reaction_report(engine.state,args.index,candles[args.index])
        if waiting is not None:
            print(json.dumps(waiting, ensure_ascii=False, default=str))
        print(f"Pending origin breaks: {int(engine.state.pending_origin_break is not None)}")
        print(f"Resolved origin breaks: {len(engine.state.resolved_origin_breaks)}")
        for report in engine.state.resolved_origin_breaks:
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
                item = {"zone_id":zone.id, "interaction_id":interaction.id}
                confirmation = next((entry for entry in getattr(state, "reaction_confirmations", [])
                                     if entry["interaction_id"] == interaction.id), None)
                if confirmation is not None:
                    item["departure_index"] = confirmation["departure_index"]
                accepted.append(item)
    invalid = [{"zone_id":reaction["zone_id"], "interaction_id":reaction["interaction_id"],
                "invalidated_at":reaction["break_index"]}
               for reaction in state.invalidated_reactions
               if reaction["reaction_index"] == index
               and reaction["reaction_type"] == reversal.type.value]
    result["valid_reactions_at_c2"] = accepted
    result["later_invalidated_reactions_at_c2"] = invalid
    result["c3_check"] = (
        ("opposite_reaction_confirmed_next_candle"
         if all(item.get("departure_index", index+1) == index+1 for item in accepted)
         else "opposite_reaction_confirmed_after_later_close") if accepted else
        "opposite_reaction_later_invalidated" if invalid else
        "opposite_pattern_without_retained_reaction"
    )
    return result


if __name__ == "__main__":
    main()
