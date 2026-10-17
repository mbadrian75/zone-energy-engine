"""Read-only replay to capture exact V1 failure context, without changing V1.

Writes only a new local JSON diagnostic file. Never writes MongoDB results or
market data. No candles or exceptions are skipped. Stops on the first failure.
"""
import argparse
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
import json
import os
from pathlib import Path
import sys
import traceback


def json_value(value):
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(v) for v in value]
    return value


def zone_identity(zone):
    names = ("id", "type", "state", "lower_price", "upper_price",
             "creation_extreme", "creation_index", "created_at_index")
    return {name: json_value(getattr(zone, name)) for name in names if hasattr(zone, name)}


def failure_context(error):
    report = {"error_type": type(error).__name__, "error": str(error),
              "traceback": "".join(traceback.format_exception(error))}
    tb = error.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        filename = frame.f_code.co_filename.replace("\\", "/")
        name, values = frame.f_code.co_name, frame.f_locals
        if filename.endswith("/v1_adapter.py") and name == "on_closed_bar":
            report["timeframe"] = values["timeframe"]
            report["requested_closed_bar"] = json_value(values["bar"])
        if filename.endswith("/replay/replay_engine.py") and name == "_process_once":
            report["failed_internal_candle"] = json_value(values["candle"])
            report["failed_internal_index"] = values.get("index")
        if filename.endswith("/replay/replay_engine.py") and name == "_activate_pending":
            report["pending_reaction"] = json_value(values.get("candidate"))
        if filename.endswith("/engine/interaction_closer.py") and name == "close":
            interaction = values["interaction"]
            report["interaction"] = json_value(interaction)
            report["origin_zone"] = zone_identity(values["origin_zone"])
            report["endpoint_zone"] = zone_identity(values["opposite_zone"])
            report["end_price"] = values.get("end_price")
            report["end_index"] = values.get("end_index")
            report["distance"] = values.get("distance")
            report["movement_time"] = values.get("movement_time")
        tb = tb.tb_next
    return report


def main():
    v2 = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(v2))
    sys.path.insert(0, str(v2.parent / "V1" / "src"))
    from run_v1_multitimeframe import utc_date
    from multi_timeframe_replay import MultiTimeframeReplay, TIMEFRAMES
    from market_streams import completed_bars
    from v1_adapter import V1ZoneEngineAdapter, DURATION
    from zone_energy.data import MarketDataRepository
    from zone_energy.engine.zone_boundary_service import ZoneBoundaryService

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=utc_date, required=True)
    parser.add_argument("--end", type=utc_date, required=True)
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year-candles-h1", type=int, default=5933)
    parser.add_argument("--year-candles-h4", type=int, default=1601)
    parser.add_argument("--year-candles-d1", type=int, default=313)
    parser.add_argument("--progress-every", type=int, default=1000)
    args = parser.parse_args()
    counts = {tf: getattr(args, "year_candles_" + tf.lower()) for tf in TIMEFRAMES}
    if args.start >= args.end or any(n <= 0 for n in counts.values()) or args.progress_every <= 0:
        parser.error("Invalid interval, yearly counts or progress interval")
    # Claim output before reading market data; never overwrite an existing report.
    with args.output.open("x", encoding="utf-8") as output:
        market = None
        count, last_at = 0, None
        try:
            market = MarketDataRepository(os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/"), args.database)
            market.ping()
            streams = {tf: completed_bars(tf, market.stream_candles(tf,
                (args.start - DURATION[tf]).replace(tzinfo=None), args.end.replace(tzinfo=None)),
                start=args.start, end=args.end) for tf in TIMEFRAMES}
            adapter = V1ZoneEngineAdapter(lambda tf, config: ZoneBoundaryService(market, config), counts)
            for point in MultiTimeframeReplay(streams, adapter).run():
                count += 1
                last_at = point.at.isoformat()
                if count % args.progress_every == 0:
                    print(f"Read-only decisions: {count}; last H1: {last_at}", flush=True)
        except Exception as error:
            report = failure_context(error)
            report.update(status="failed", completed_h1_decisions=count, last_successful_h1=last_at,
                          start=args.start.isoformat(), end=args.end.isoformat(), year_candles=counts)
            json.dump(report, output, indent=2, ensure_ascii=False, allow_nan=False)
            output.flush()
            summary = {k: report[k] for k in ("error", "timeframe", "failed_internal_candle",
                "failed_internal_index", "distance", "movement_time", "end_price", "end_index") if k in report}
            print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)
            print(f"Diagnostic report: {args.output.resolve()}", flush=True)
            return 1
        else:
            json.dump(dict(status="completed", completed_h1_decisions=count, last_successful_h1=last_at), output, indent=2)
            print(f"Read-only replay completed: {count} decisions; report: {args.output.resolve()}")
            return 0
        finally:
            if market is not None:
                market.close()


if __name__ == "__main__":
    raise SystemExit(main())
