import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.zone_contact_detector import (
    ZoneContactDetector,
)
from zone_energy.models import (
    Candle,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone() -> Zone:
    return Zone(
        id=1,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )


def make_candle(
    low: float,
    high: float,
) -> Candle:
    midpoint = (low + high) / 2

    return Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=midpoint,
        high=high,
        low=low,
        close=midpoint,
        volume=0.0,
    )


def test_candle_inside_zone():
    zone = make_zone()

    candle = make_candle(
        low=102.0,
        high=108.0,
    )

    assert ZoneContactDetector.has_contact(
        zone=zone,
        candle=candle,
    )

    print("Candle inside zone: PASS")


def test_touch_lower_boundary():
    zone = make_zone()

    candle = make_candle(
        low=95.0,
        high=100.0,
    )

    assert ZoneContactDetector.has_contact(
        zone=zone,
        candle=candle,
    )

    print("Touch lower boundary: PASS")


def test_touch_upper_boundary():
    zone = make_zone()

    candle = make_candle(
        low=110.0,
        high=115.0,
    )

    assert ZoneContactDetector.has_contact(
        zone=zone,
        candle=candle,
    )

    print("Touch upper boundary: PASS")


def test_candle_crosses_entire_zone():
    zone = make_zone()

    candle = make_candle(
        low=95.0,
        high=115.0,
    )

    assert ZoneContactDetector.has_contact(
        zone=zone,
        candle=candle,
    )

    print("Candle crosses entire zone: PASS")


def test_no_contact_below_zone():
    zone = make_zone()

    candle = make_candle(
        low=90.0,
        high=99.0,
    )

    assert not ZoneContactDetector.has_contact(
        zone=zone,
        candle=candle,
    )

    print("No contact below zone: PASS")


def test_no_contact_above_zone():
    zone = make_zone()

    candle = make_candle(
        low=111.0,
        high=120.0,
    )

    assert not ZoneContactDetector.has_contact(
        zone=zone,
        candle=candle,
    )

    print("No contact above zone: PASS")


def main():
    test_candle_inside_zone()

    test_touch_lower_boundary()
    test_touch_upper_boundary()

    test_candle_crosses_entire_zone()

    test_no_contact_below_zone()
    test_no_contact_above_zone()

    print(
        "\nAll ZoneContactDetector tests: PASS"
    )


if __name__ == "__main__":
    main()