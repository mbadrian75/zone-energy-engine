"""Read-only energy trace, reconstructing past a saved checkpoint without writes."""
import argparse
from dataclasses import asdict, fields
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from zone_energy.config import EngineConfig,EngineTimeframe
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from zone_energy.replay.replay_engine import ReplayEngine,ReplayState


def interaction_report(state, identifier):
    matches = [(zone,move) for zone in state.zones for move in zone.interactions if move.id==identifier]
    if len(matches)!=1:
        raise ValueError("Requested interaction is not uniquely retained in reconstructed history")
    zone,move = matches[0]
    report = {"zone_id":zone.id,"zone_type_at_inspection":zone.type.value,
              "interaction":asdict(move),"broken_zone_histories":[]}
    for record in move.breaks:
        target = next(zone for zone in state.zones if zone.id==record.broken_zone_id)
        # These are retained historical movements; the immutable break reference
        # is authoritative, not a recomputation from later finalized history.
        history = [{"interaction_id":item.id,"start_index":item.start_index,"end_index":item.end_index,
                    "movement_energy":item.movement_energy,"total_break_evidence":item.total_break_evidence,
                    "base_energy":item.base_energy,"breaks": [asdict(entry) for entry in item.breaks]}
                   for item in target.interactions if item.end_index is not None and item.end_index<=record.break_index]
        report["broken_zone_histories"].append({"zone_id":target.id,"break_index":record.break_index,
            "stored_energy":record.broken_zone_energy_at_break,
            "stored_median":record.median_active_zone_energy_at_break,
            "retained_movements_ending_by_break":history})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--checkpoint-index",type=int,required=True)
    parser.add_argument("--through-index",type=int,required=True)
    parser.add_argument("--interaction-id",type=int,required=True)
    parser.add_argument("--timeframe",default="H1")
    parser.add_argument("--database",default="market_data")
    args = parser.parse_args()
    if not 0 <= args.checkpoint_index <= args.through_index:
        parser.error("through-index must be at or after checkpoint-index")
    from zone_energy.data import EngineResultsRepository,MarketDataRepository
    uri = os.environ.get("ZONE_ENERGY_MONGO_URI","mongodb://localhost:27017/")
    market = MarketDataRepository(uri,args.database)
    results = EngineResultsRepository(uri,args.database)
    try:
        identifier = json.dumps([args.run_id,"XAUUSD",args.timeframe,args.checkpoint_index],separators=(",",":"))
        document = results.get_checkpoint(identifier)
        if document is None:
            raise ValueError("Checkpoint not found")
        context = document["replay_context"]
        config_values = dict(document["config"])
        config_values.setdefault("barrier_cost_transform","power")
        config_values["timeframe"] = EngineTimeframe(config_values["timeframe"])
        config = EngineConfig(**config_values)
        engine = ReplayEngine(config,document["year_candles"],ZoneBoundaryService(market,config))
        for candle in market.stream_candles(args.timeframe,context["start"],context["end"]):
            engine.process(candle)
            if engine.current_index==args.checkpoint_index:
                if (engine.state.zones != results.load_zones(identifier)
                        or candle.datetime != context["candle_datetime"]
                        or any(getattr(engine.state,item.name) != context.get(item.name,item.default_factory()
                            if callable(item.default_factory) else item.default)
                            for item in fields(ReplayState) if item.name != "zones")):
                    raise ValueError("Checkpoint reconstruction differs; trace withheld")
                print("Checkpoint reconstruction: MATCH")
            if engine.current_index==args.through_index:
                break
        if engine.current_index!=args.through_index:
            raise ValueError("Requested candle index unavailable")
        print(f"Read-only reconstruction through index: {engine.current_index}")
        print(json.dumps(interaction_report(engine.state,args.interaction_id),ensure_ascii=False,indent=2,default=str))
    finally:
        results.close()
        market.close()


if __name__ == "__main__":
    main()
