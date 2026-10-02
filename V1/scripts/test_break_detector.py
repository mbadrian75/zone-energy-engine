import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.break_detector import BreakDetector
from zone_energy.models import (
    Candle,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone(
    zone_type: ZoneType,
    state: ZoneState = ZoneState.ACTIVE,
) -> Zone:
    return Zone(
        id=1,
        type=zone_type,
        state=state,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=(
            100.0
            if zone_type == ZoneType.SUPPORT
            else 110.0
        ),
        creation_index=10,
        created_at_index=11,
    )


def make_candle(
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=0.0,
    )


def test_valid_support_break():
    zone = make_zone(ZoneType.SUPPORT)

    candle = make_candle(
        open_price=99.0,
        high=99.5,
        low=95.0,
        close=96.0,
    )

    assert BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Valid support break: PASS")


def test_valid_resistance_break():
    zone = make_zone(ZoneType.RESISTANCE)

    candle = make_candle(
        open_price=111.0,
        high=115.0,
        low=110.5,
        close=114.0,
    )

    assert BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Valid resistance break: PASS")


def test_support_wick_only():
    zone = make_zone(ZoneType.SUPPORT)

    candle = make_candle(
        open_price=105.0,
        high=106.0,
        low=95.0,
        close=102.0,
    )

    assert not BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Support wick-only: PASS")


def test_resistance_wick_only():
    zone = make_zone(ZoneType.RESISTANCE)

    candle = make_candle(
        open_price=105.0,
        high=115.0,
        low=104.0,
        close=108.0,
    )

    assert not BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Resistance wick-only: PASS")


def test_support_body_on_boundary():
    zone = make_zone(ZoneType.SUPPORT)

    candle = make_candle(
        open_price=100.0,
        high=101.0,
        low=95.0,
        close=96.0,
    )

    assert not BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Support body on boundary: PASS")


def test_resistance_body_on_boundary():
    zone = make_zone(ZoneType.RESISTANCE)

    candle = make_candle(
        open_price=110.0,
        high=115.0,
        low=109.0,
        close=114.0,
    )

    assert not BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Resistance body on boundary: PASS")


def test_wrong_candle_direction():
    support = make_zone(ZoneType.SUPPORT)

    bullish_below_support = make_candle(
        open_price=96.0,
        high=99.0,
        low=95.0,
        close=98.0,
    )

    assert not BreakDetector.is_broken(
        support,
        bullish_below_support,
    )

    resistance = make_zone(
        ZoneType.RESISTANCE
    )

    bearish_above_resistance = make_candle(
        open_price=114.0,
        high=115.0,
        low=110.5,
        close=111.0,
    )

    assert not BreakDetector.is_broken(
        resistance,
        bearish_above_resistance,
    )

    print("Wrong candle direction: PASS")


def test_broken_zone_is_ignored():
    zone = make_zone(
        ZoneType.RESISTANCE,
        state=ZoneState.BROKEN,
    )

    candle = make_candle(
        open_price=111.0,
        high=115.0,
        low=110.5,
        close=114.0,
    )

    assert not BreakDetector.is_broken(
        zone,
        candle,
    )

    print("Already broken zone ignored: PASS")


def main():
    test_valid_support_break()
    test_valid_resistance_break()

    test_support_wick_only()
    test_resistance_wick_only()

    test_support_body_on_boundary()
    test_resistance_body_on_boundary()

    test_wrong_candle_direction()
    test_broken_zone_is_ignored()

    print(
        "\nAll BreakDetector tests: PASS"
    )


if __name__ == "__main__":
    main()