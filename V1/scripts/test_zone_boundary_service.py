import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.config import (
    EngineConfig,
    EngineTimeframe,
)
from zone_energy.data import MarketDataRepository
from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.engine.zone_boundary_service import ZoneBoundaryService


def main():
    repository = MarketDataRepository()

    try:
        repository.ping()
        print("MongoDB connection: PASS")

        config = EngineConfig(
            timeframe=EngineTimeframe.H1
        )

        boundary_service = ZoneBoundaryService(
            repository=repository,
            config=config,
        )

        candles = repository.get_candles(
            timeframe="H1",
            start=datetime(2025, 1, 1),
            end=datetime(2025, 2, 1),
        )

        print(f"H1 candles loaded: {len(candles)}")

        if len(candles) < 3:
            raise RuntimeError(
                "Not enough H1 candles for reversal detection."
            )

        reversal_count = 0
        boundary_count = 0

        for index in range(2, len(candles)):
            c1 = candles[index - 2]
            c2 = candles[index - 1]
            c3 = candles[index]

            reversal = ReversalDetector.detect(
                c1=c1,
                c2=c2,
                c3=c3,
                c1_index=index - 2,
                c2_index=index - 1,
                c3_index=index,
            )

            if reversal is None:
                continue

            reversal_count += 1

            boundary = boundary_service.resolve(
                reversal=reversal,
                origin_candle=c2,
            )

            if boundary is None:
                continue

            boundary_count += 1

            lower_price, upper_price = boundary

            print("\nReal reversal with M15 boundary found:")
            print(f"Type: {reversal.type}")
            print(f"C2 datetime: {c2.datetime}")
            print(f"Extreme price: {reversal.extreme_price}")
            print(f"Lower boundary: {lower_price}")
            print(f"Upper boundary: {upper_price}")
            print(f"Zone height: {upper_price - lower_price}")

            assert upper_price > lower_price

            if reversal.type.value == "support":
                assert (
                    abs(
                        lower_price
                        - reversal.extreme_price
                    )
                    <= config.extreme_price_tolerance
                )

            else:
                assert (
                    abs(
                        upper_price
                        - reversal.extreme_price
                    )
                    <= config.extreme_price_tolerance
                )

            print("\nReal MongoDB boundary test: PASS")
            break

        else:
            raise RuntimeError(
                "No reversal with matching M15 boundary "
                "was found in the selected period."
            )

        print(
            f"\nReversals checked before match: "
            f"{reversal_count}"
        )

        print(
            f"Boundaries found: "
            f"{boundary_count}"
        )

    finally:
        repository.close()


if __name__ == "__main__":
    main()