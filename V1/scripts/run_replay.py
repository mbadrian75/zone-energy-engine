"""Replay XAUUSD candles from MongoDB and persist results in the same database."""

import argparse
from datetime import datetime
import os
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.data import EngineResultsRepository, MarketDataRepository
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService
from zone_energy.replay.replay_runner import ReplayRunner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, type=datetime.fromisoformat)
    parser.add_argument("--end", required=True, type=datetime.fromisoformat)
    parser.add_argument("--timeframe", choices=[item.value for item in EngineTimeframe], default="H1")
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--checkpoint-every", type=int, default=100)
    horizon = parser.add_mutually_exclusive_group(required=True)
    horizon.add_argument("--year-candles", type=int)
    horizon.add_argument("--reference-year", type=int,
                         help="Count actual candles in a fully populated reference year")
    args = parser.parse_args()
    uri = os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/")
    market = MarketDataRepository(uri, args.database)
    results = EngineResultsRepository(uri, args.database)
    try:
        market.ping()
        count = args.year_candles
        if args.reference_year is not None:
            count = len(market.get_candles(args.timeframe,
                datetime(args.reference_year, 1, 1), datetime(args.reference_year + 1, 1, 1)))
            print(f"Actual reference-year candles: {count}", flush=True)
        run_id = args.run_id or "replay-" + uuid4().hex
        print(f"Run ID: {run_id}", flush=True)
        config = EngineConfig(timeframe=EngineTimeframe(args.timeframe))
        runner = ReplayRunner(market, results, ZoneBoundaryService(market, config), config, count)
        summary = runner.run(start=args.start, end=args.end, run_id=run_id,
                             checkpoint_every=args.checkpoint_every)
        for key, value in summary.items():
            print(f"{key}: {value}")
    finally:
        results.close()
        market.close()


if __name__ == "__main__":
    main()
