"""Replay XAUUSD with V1 engines and persist H1 decisions to JSONL or MongoDB."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "V1" / "src"))

from multi_timeframe_replay import MultiTimeframeReplay, TIMEFRAMES
from market_streams import completed_bars
from v1_adapter import V1ZoneEngineAdapter, DURATION
from zone_energy.data import MarketDataRepository
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from mongo_result_repository import MongoV2ResultRepository
from mongo_event_repository import MongoEventRepository
from validate_event_run import require_validated_smoke


def utc_date(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Invalid ISO date/time") from exc
    if parsed.tzinfo is not None:
        raise argparse.ArgumentTypeError("Use UTC wall-time without timezone suffix")
    return parsed.replace(tzinfo=timezone.utc)


def report_progress(points, every):
    for count, point in enumerate(points, 1):
        if count % every == 0:
            print(f"Processed H1 decisions: {count}; last H1: {point.at.isoformat()}", flush=True)
        yield point


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=utc_date, required=True)
    parser.add_argument("--end", type=utc_date, required=True)
    parser.add_argument("--year-candles-h1", type=int, required=True)
    parser.add_argument("--year-candles-h4", type=int, required=True)
    parser.add_argument("--year-candles-d1", type=int, required=True)
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--storage", choices=("jsonl", "mongodb", "mongodb-events"), default="jsonl")
    parser.add_argument("--output", type=Path, help="Required only for --storage jsonl")
    parser.add_argument("--run-id", help="Unique identifier for --storage mongodb")
    parser.add_argument("--mongo-batch-size", type=int, default=25)
    parser.add_argument("--event-batch-size", type=int, default=1000)
    parser.add_argument("--progress-every", type=int, default=1000,
                        help="Print processed H1 progress in event mode (not a commit marker)")
    parser.add_argument("--validated-smoke-run-id",
                        help="Completed January schema-3 smoke required for event replays over 31 days")
    args = parser.parse_args()
    if args.start >= args.end:
        parser.error("--start must be before --end")
    year_counts = {tf: getattr(args, "year_candles_" + tf.lower()) for tf in TIMEFRAMES}
    if any(count <= 0 for count in year_counts.values()):
        parser.error("All year-candle counts must be positive")
    if args.storage == "jsonl" and args.output is None:
        parser.error("--output is required for JSONL")
    if args.storage != "jsonl" and args.output is not None:
        parser.error("Do not pass --output when storing in MongoDB")
    if args.mongo_batch_size <= 0:
        parser.error("--mongo-batch-size must be positive")
    if args.event_batch_size <= 0:
        parser.error("--event-batch-size must be positive")
    if args.progress_every <= 0:
        parser.error("--progress-every must be positive")

    mongo_uri = os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/")
    market = MarketDataRepository(mongo_uri, args.database)
    results = None
    try:
        market.ping()
        streams = {
            tf: completed_bars(
                tf,
                market.stream_candles(
                    tf,
                    (args.start - DURATION[tf]).replace(tzinfo=None),
                    args.end.replace(tzinfo=None),
                ),
                start=args.start, end=args.end,
            ) for tf in TIMEFRAMES
        }
        adapter = V1ZoneEngineAdapter(
            lambda tf, config: ZoneBoundaryService(market, config), year_counts
        )
        decisions = MultiTimeframeReplay(streams, adapter).run()
        if args.storage != "jsonl":
            run_id = args.run_id or "xauusd-v2-" + uuid4().hex
            if args.storage == "mongodb-events":
                results = MongoEventRepository(mongo_uri=mongo_uri, database=args.database,
                                               event_batch_size=args.event_batch_size)
                if args.end - args.start > timedelta(days=31):
                    report = require_validated_smoke(results, args.validated_smoke_run_id, year_counts)
                    print(f"January equivalence gate passed: {report['decisions']} decisions", flush=True)
                decisions = MultiTimeframeReplay(streams, adapter,
                    on_observation=lambda tf, at, state: results.observe(tf, at, state,
                        rejections=adapter.recent_rejections(tf))).run()
                decisions = report_progress(decisions, args.progress_every)
            else:
                results = MongoV2ResultRepository(mongo_uri=mongo_uri, database=args.database)
            results.begin_run(run_id=run_id, start=args.start, end=args.end,
                              year_candles=year_counts)
            print(f"MongoDB run_id: {run_id}", flush=True)
            try:
                results.append_points(decisions, batch_size=args.mongo_batch_size)
                count = results.finish_run()
            except Exception as exc:
                results.fail_run(exc)
                raise
            print(f"H1 decision snapshots: {count}; MongoDB run_id: {run_id}")
        else:
            count = 0
            # 'x' avoids overwriting previously recorded snapshots.
            with args.output.open("x", encoding="utf-8") as output:
                for point in decisions:
                    output.write(json.dumps({
                        "symbol": "XAUUSD",
                        "decision_at": point.at.isoformat(),
                        "last_closed_at": {
                            tf: stamp.isoformat() if stamp else None
                            for tf, stamp in point.last_closed_at.items()
                        },
                        "timeframes": point.zones,
                    }, ensure_ascii=False, allow_nan=False) + "\n")
                    count += 1
            print(f"H1 decision snapshots: {count}; output: {args.output}")
    finally:
        if results is not None:
            results.close()
        market.close()


if __name__ == "__main__":
    main()
