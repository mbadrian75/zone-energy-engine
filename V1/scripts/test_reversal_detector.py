import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.models import Candle, ZoneType


def make_candle(
    open_: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(
        datetime=datetime(2025, 1, 1),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=0.0,
    )


def test_resistance():
    c1 = make_candle(100, 105, 99, 103)
    c2 = make_candle(103, 110, 102, 108)
    c3 = make_candle(106, 107, 101, 104)

    reversal = ReversalDetector.detect(
        c1=c1,
        c2=c2,
        c3=c3,
        c1_index=100,
        c2_index=101,
        c3_index=102,
    )

    assert reversal is not None
    assert reversal.type == ZoneType.RESISTANCE
    assert reversal.extreme_price == 110
    assert reversal.extreme_index == 101
    assert reversal.detection_index == 102

    print("Resistance reversal: PASS")


def test_support():
    c1 = make_candle(105, 108, 100, 103)
    c2 = make_candle(103, 106, 95, 98)
    c3 = make_candle(98, 104, 97, 102)

    reversal = ReversalDetector.detect(
        c1=c1,
        c2=c2,
        c3=c3,
        c1_index=200,
        c2_index=201,
        c3_index=202,
    )

    assert reversal is not None
    assert reversal.type == ZoneType.SUPPORT
    assert reversal.extreme_price == 95
    assert reversal.extreme_index == 201
    assert reversal.detection_index == 202

    print("Support reversal: PASS")


def test_no_reversal():
    c1 = make_candle(100, 105, 99, 103)
    c2 = make_candle(103, 106, 100, 104)
    c3 = make_candle(104, 107, 101, 106)

    reversal = ReversalDetector.detect(
        c1=c1,
        c2=c2,
        c3=c3,
        c1_index=300,
        c2_index=301,
        c3_index=302,
    )

    assert reversal is None

    print("No reversal: PASS")


def test_ambiguous_reversal():
    c1 = make_candle(100, 105, 95, 102)

    # C2 has both:
    # a higher high than C1/C3
    # and a lower low than C1/C3
    c2 = make_candle(102, 110, 90, 101)

    c3 = make_candle(101, 106, 96, 103)

    reversal = ReversalDetector.detect(
        c1=c1,
        c2=c2,
        c3=c3,
        c1_index=400,
        c2_index=401,
        c3_index=402,
    )

    assert reversal is None

    print("Ambiguous reversal ignored: PASS")


def main():
    test_resistance()
    test_support()
    test_no_reversal()
    test_ambiguous_reversal()

    print("\nAll reversal detector tests: PASS")


if __name__ == "__main__":
    main()