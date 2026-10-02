import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.config import EngineConfig
from zone_energy.engine.zone_boundary_detector import ZoneBoundaryDetector
from zone_energy.models import (
    Candle,
    Reversal,
    ZoneType,
)


def make_candle(
    minute: int,
    open_: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(
        datetime=datetime(2025, 1, 1, 10, minute),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=0.0,
    )


def test_support_boundary():
    config = EngineConfig()
    detector = ZoneBoundaryDetector(config)

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=100.0,
        extreme_index=100,
        detection_index=101,
    )

    m15_candles = [
        make_candle(
            minute=30,
            open_=104.0,
            high=106.0,
            low=100.0,
            close=103.0,
        ),
        make_candle(
            minute=0,
            open_=103.0,
            high=105.0,
            low=101.0,
            close=104.0,
        ),
        make_candle(
            minute=15,
            open_=102.0,
            high=104.0,
            low=100.0,
            close=103.0,
        ),
    ]

    boundary = detector.detect(
        reversal=reversal,
        m15_candles=m15_candles,
    )

    assert boundary == (100.0, 104.0)

    print("Support boundary: PASS")


def test_resistance_boundary():
    config = EngineConfig()
    detector = ZoneBoundaryDetector(config)

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=110.0,
        extreme_index=200,
        detection_index=201,
    )

    m15_candles = [
        make_candle(
            minute=30,
            open_=106.0,
            high=110.0,
            low=104.0,
            close=108.0,
        ),
        make_candle(
            minute=0,
            open_=104.0,
            high=108.0,
            low=103.0,
            close=107.0,
        ),
        make_candle(
            minute=15,
            open_=107.0,
            high=110.0,
            low=105.0,
            close=109.0,
        ),
    ]

    boundary = detector.detect(
        reversal=reversal,
        m15_candles=m15_candles,
    )

    assert boundary == (105.0, 110.0)

    print("Resistance boundary: PASS")


def test_tolerance():
    config = EngineConfig(
        extreme_price_tolerance=0.001
    )
    detector = ZoneBoundaryDetector(config)

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=100.0,
        extreme_index=300,
        detection_index=301,
    )

    m15_candles = [
        make_candle(
            minute=0,
            open_=102.0,
            high=104.0,
            low=100.0005,
            close=103.0,
        ),
    ]

    boundary = detector.detect(
        reversal=reversal,
        m15_candles=m15_candles,
    )

    assert boundary == (100.0005, 104.0)

    print("Tolerance matching: PASS")


def test_no_match():
    config = EngineConfig()
    detector = ZoneBoundaryDetector(config)

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=100.0,
        extreme_index=400,
        detection_index=401,
    )

    m15_candles = [
        make_candle(
            minute=0,
            open_=103.0,
            high=105.0,
            low=101.0,
            close=104.0,
        ),
    ]

    boundary = detector.detect(
        reversal=reversal,
        m15_candles=m15_candles,
    )

    assert boundary is None

    print("No matching M15 candle: PASS")


def main():
    test_support_boundary()
    test_resistance_boundary()
    test_tolerance()
    test_no_match()

    print("\nAll zone boundary detector tests: PASS")


if __name__ == "__main__":
    main()