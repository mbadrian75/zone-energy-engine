"""Stream V1 XAUUSD Mongo data through the V2 multi-timeframe decision clock."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "V1" / "src"))

from multi_timeframe_replay import MultiTimeframeReplay, TIMEFRAMES
from market_streams import completed_bars
from v1_adapter import V1ZoneEngineAdapter, DURATION
from zone_energy.data import MarketDataRepository
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService


def utc_date(text: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Invalid ISO date/time") from exc
    if parsed.tzinfo is not None:
        raise argparse.ArgumentTypeError("Use UTC wall-time without timezone suffix")
    return parsed.replace(tzinfo=timezone.utc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=utc_date, required=True)
    parser.add_argument("--end", type=utc_date, required=True)
    parser.add_argument("--year-candles-h1", type=int, required=True)
    parser.add_argument("--year-candles-h4", type=int, required=True)
    parser.add_argument("--year-candles-d1", type=int, required=True)
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.start >= args.end:
        parser.error("--start must be before --end")
    year_counts = {tf: getattr(args, "year_candles_" + tf.lower()) for tf in TIMEFRAMES}
    if any(count <= 0 for count in year_counts.values()):
        parser.error("All year-candle counts must be positive")

    market = MarketDataRepository(
        os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/"),
        args.database,
    )
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
        count = 0
        # 'x' avoids overwriting previously recorded snapshots.
        with args.output.open("x", encoding="utf-8") as output:
            for point in MultiTimeframeReplay(streams, adapter).run():
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
        market.close()


if __name__ == "__main__":
    main()
