import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.break_displacement_calculator import (
    BreakDisplacementCalculator,
)
from zone_energy.models import (
    Candle,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone(
    zone_type: ZoneType,
) -> Zone:
    return Zone(
        id=1,
        type=zone_type,
        state=ZoneState.ACTIVE,
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


def test_support_displacement():
    zone = make_zone(
        ZoneType.SUPPORT
    )

    candle = make_candle(
        open_price=99.0,
        high=99.5,
        low=94.0,
        close=95.0,
    )

    displacement, ratio = (
        BreakDisplacementCalculator.calculate(
            zone=zone,
            break_candle=candle,
        )
    )

    assert displacement == 5.0
    assert ratio == 0.5

    print("Support displacement: PASS")


def test_resistance_displacement():
    zone = make_zone(
        ZoneType.RESISTANCE
    )

    candle = make_candle(
        open_price=111.0,
        high=116.0,
        low=110.5,
        close=115.0,
    )

    displacement, ratio = (
        BreakDisplacementCalculator.calculate(
            zone=zone,
            break_candle=candle,
        )
    )

    assert displacement == 5.0
    assert ratio == 0.5

    print("Resistance displacement: PASS")


def test_zero_displacement():
    zone = make_zone(
        ZoneType.RESISTANCE
    )

    candle = make_candle(
        open_price=109.0,
        high=111.0,
        low=108.0,
        close=110.0,
    )

    displacement, ratio = (
        BreakDisplacementCalculator.calculate(
            zone=zone,
            break_candle=candle,
        )
    )

    assert displacement == 0.0
    assert ratio == 0.0

    print("Zero displacement: PASS")


def test_negative_support_displacement_rejected():
    zone = make_zone(
        ZoneType.SUPPORT
    )

    candle = make_candle(
        open_price=101.0,
        high=106.0,
        low=100.0,
        close=105.0,
    )

    try:
        BreakDisplacementCalculator.calculate(
            zone=zone,
            break_candle=candle,
        )
    except ValueError:
        print(
            "Negative support displacement rejected: PASS"
        )
    else:
        raise AssertionError(
            "Negative displacement must raise ValueError"
        )


def test_negative_resistance_displacement_rejected():
    zone = make_zone(
        ZoneType.RESISTANCE
    )

    candle = make_candle(
        open_price=109.0,
        high=109.5,
        low=104.0,
        close=105.0,
    )

    try:
        BreakDisplacementCalculator.calculate(
            zone=zone,
            break_candle=candle,
        )
    except ValueError:
        print(
            "Negative resistance displacement rejected: PASS"
        )
    else:
        raise AssertionError(
            "Negative displacement must raise ValueError"
        )


def main():
    test_support_displacement()
    test_resistance_displacement()

    test_zero_displacement()

    test_negative_support_displacement_rejected()
    test_negative_resistance_displacement_rejected()

    print(
        "\nAll BreakDisplacementCalculator tests: PASS"
    )


if __name__ == "__main__":
    main()