import sys
from datetime import datetime
from pathlib import Path


V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))


from zone_energy.data import MarketDataRepository


def main():
    repository = MarketDataRepository()

    try:
        repository.ping()
        print("MongoDB connection: OK")

        candles = repository.get_candles(
            timeframe="H1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 2),
        )

        print(f"\nCandles loaded: {len(candles)}")

        for candle in candles[:10]:
            print(
                candle.datetime,
                f"O={candle.open}",
                f"H={candle.high}",
                f"L={candle.low}",
                f"C={candle.close}",
                f"V={candle.volume}",
            )

    finally:
        repository.close()


if __name__ == "__main__":
    main()