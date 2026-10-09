"""Summarize final checkpoint energy and immutable historical break values."""
import argparse
import json
from math import isfinite
from pathlib import Path
import os
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from zone_energy.config import EngineConfig,EngineTimeframe
from zone_energy.data import EngineResultsRepository
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator


def distribution(values):
    items = list(values)
    known = sorted(value for value in items if value is not None)
    if any(not isfinite(value) or value < 0 for value in known):
        raise ValueError("Nonfinite or negative energy found; report withheld")
    def percentile(q):
        if not known:
            return None
        position = (len(known)-1)*q
        lower = int(position)
        upper = min(lower+1,len(known)-1)
        return known[lower]+(known[upper]-known[lower])*(position-lower)
    return {"total":len(items),"defined":len(known),"undefined":len(items)-len(known),
            "zero":sum(value==0 for value in known),"min":known[0] if known else None,
            "median":percentile(.5),"p95":percentile(.95),"p99":percentile(.99),
            "max":known[-1] if known else None}


def summarize(zones,config,index,year_candles):
    calculator = EffectiveZoneEnergyCalculator(config)
    energies = [{"zone_id":zone.id,"type":zone.type.value,"state":zone.state.value,
                 "creation_index":zone.creation_index,"energy":calculator.calculate(zone,index,year_candles)}
                for zone in zones]
    interactions = [(zone,move) for zone in zones for move in zone.interactions]
    breaks = [(zone,move,record) for zone,move in interactions for record in move.breaks]
    key = lambda row: row["energy"] if row["energy"] is not None else -1
    base_rows = [{"zone_id":zone.id,"interaction_id":move.id,"start_index":move.start_index,
                  "end_index":move.end_index,"base_energy":move.base_energy,
                  "movement_energy":move.movement_energy,"total_break_evidence":move.total_break_evidence}
                 for zone,move in interactions if move.base_energy is not None]
    break_rows = [{"origin_zone_id":zone.id,"interaction_id":move.id,
                   "broken_zone_id":record.broken_zone_id,"break_index":record.break_index,
                   "zone_energy_at_break":record.broken_zone_energy_at_break,
                   "median_at_break":record.median_active_zone_energy_at_break,
                   "barrier_ratio":record.barrier_ratio,"barrier_cost":record.barrier_cost,
                   "break_evidence":record.break_evidence} for zone,move,record in breaks]
    return {"scope":"Final retained checkpoint history; final zone energies are not intrayear maxima",
        "calibration":config.barrier_cost_transform,
        "final_zone_energy":distribution(row["energy"] for row in energies),
        "final_active_zone_energy":distribution(row["energy"] for row in energies if row["state"]=="active"),
        "final_broken_zone_energy":distribution(row["energy"] for row in energies if row["state"]=="broken"),
        "interaction_base_energy":distribution(move.base_energy for _,move in interactions),
        "movement_energy":distribution(move.movement_energy for _,move in interactions),
        "barrier_ratio":distribution(record.barrier_ratio for _,_,record in breaks),
        "barrier_cost":distribution(record.barrier_cost for _,_,record in breaks),
        "break_evidence":distribution(record.break_evidence for _,_,record in breaks),
        "top_final_zones":sorted(energies,key=key,reverse=True)[:10],
        "top_interactions":sorted(base_rows,key=lambda row:row["base_energy"],reverse=True)[:10],
        "top_breaks":sorted(break_rows,key=lambda row:row["break_evidence"]
                             if row["break_evidence"] is not None else -1,reverse=True)[:10],
        "zone_energies_for_verification":energies}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id",required=True)
    parser.add_argument("--index",type=int,required=True)
    parser.add_argument("--timeframe",default="H1")
    parser.add_argument("--database",default="market_data")
    parser.add_argument("--output",default="replay-energy-summary.json")
    args = parser.parse_args()
    repository = EngineResultsRepository(os.environ.get("ZONE_ENERGY_MONGO_URI","mongodb://localhost:27017/"),args.database)
    try:
        identity = json.dumps([args.run_id,"XAUUSD",args.timeframe,args.index],separators=(",",":"))
        document = repository.get_checkpoint(identity)
        if document is None:
            raise ValueError("Checkpoint not found")
        values = dict(document["config"])
        values["timeframe"] = EngineTimeframe(values["timeframe"])
        values.setdefault("barrier_cost_transform","power")
        report = summarize(repository.load_zones(identity),EngineConfig(**values),args.index,document["year_candles"])
        actual = sorted([{"zone_id":row["zone_id"],"energy":row["energy"]}
                         for row in report.pop("zone_energies_for_verification")],key=lambda row:row["zone_id"])
        if actual != document["effective_zone_energies"]:
            raise ValueError("Final zone energies differ from checkpoint; report withheld")
        report.update({"run_id":args.run_id,"checkpoint_index":args.index,"checkpoint_energy_match":True})
        output = Path(args.output).resolve()
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
        print("Checkpoint energy verification: MATCH")
        print(f"Report: {output}")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
