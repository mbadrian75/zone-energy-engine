import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.config import EngineTimeframe
from zone_energy.engine.timeframe_window import TimeframeWindow


def test_h1():
    candle_datetime = datetime(
        2025, 1, 1, 10, 0
    )

    start, end = TimeframeWindow.get(
        candle_datetime=candle_datetime,
        timeframe=EngineTimeframe.H1,
    )

    assert start == datetime(
        2025, 1, 1, 10, 0
    )

    assert end == datetime(
        2025, 1, 1, 11, 0
    )

    print("H1 window: PASS")


def test_h4():
    candle_datetime = datetime(
        2025, 1, 1, 8, 0
    )

    start, end = TimeframeWindow.get(
        candle_datetime=candle_datetime,
        timeframe=EngineTimeframe.H4,
    )

    assert start == datetime(
        2025, 1, 1, 8, 0
    )

    assert end == datetime(
        2025, 1, 1, 12, 0
    )

    print("H4 window: PASS")


def test_d1():
    candle_datetime = datetime(
        2025, 1, 1, 18, 0
    )

    start, end = TimeframeWindow.get(
        candle_datetime=candle_datetime,
        timeframe=EngineTimeframe.D1,
    )

    assert start == datetime(
        2025, 1, 1, 18, 0
    )

    assert end == datetime(
        2025, 1, 2, 18, 0
    )

    print("D1 window: PASS")


def main():
    test_h1()
    test_h4()
    test_d1()

    print(
        "\nAll timeframe window tests: PASS"
    )


if __name__ == "__main__":
    main()