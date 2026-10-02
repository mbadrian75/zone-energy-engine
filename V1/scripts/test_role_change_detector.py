import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.role_change_detector import (
    RoleChangeDetector,
)
from zone_energy.models import (
    Candle,
    PriceSide,
    Reversal,
    Zone,
    ZoneState,
    ZoneType,
)


def make_candles():
    c1 = Candle(
        datetime=datetime(2025, 1, 1, 10, 0),
        open=104.0,
        high=107.0,
        low=102.0,
        close=106.0,
        volume=0,
    )

    c2 = Candle(
        datetime=datetime(2025, 1, 1, 11, 0),
        open=106.0,
        high=108.0,
        low=103.0,
        close=104.0,
        volume=0,
    )

    c3 = Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=104.0,
        high=105.0,
        low=99.0,
        close=100.0,
        volume=0,
    )

    return c1, c2, c3


def test_broken_support_to_resistance():
    zone = Zone(
        id=1,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
        last_external_price_side=PriceSide.BELOW,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=108.0,
        extreme_index=20,
        detection_index=21,
    )

    c1, c2, c3 = make_candles()

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is True

    print(
        "Broken SUPPORT -> RESISTANCE role change: PASS"
    )


def test_broken_resistance_to_support():
    zone = Zone(
        id=2,
        type=ZoneType.RESISTANCE,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=110.0,
        creation_index=10,
        created_at_index=11,
        last_external_price_side=PriceSide.ABOVE,
    )

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=102.0,
        extreme_index=20,
        detection_index=21,
    )

    c1 = Candle(
        datetime=datetime(2025, 1, 1, 10, 0),
        open=106.0,
        high=111.0,
        low=103.0,
        close=104.0,
        volume=0,
    )

    c2 = Candle(
        datetime=datetime(2025, 1, 1, 11, 0),
        open=104.0,
        high=107.0,
        low=102.0,
        close=105.0,
        volume=0,
    )

    c3 = Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=105.0,
        high=109.0,
        low=104.0,
        close=108.0,
        volume=0,
    )

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is True

    print(
        "Broken RESISTANCE -> SUPPORT role change: PASS"
    )


def test_active_zone_cannot_role_change():
    zone = Zone(
        id=3,
        type=ZoneType.SUPPORT,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
        last_external_price_side=PriceSide.BELOW,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=108.0,
        extreme_index=20,
        detection_index=21,
    )

    c1, c2, c3 = make_candles()

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is False

    print(
        "ACTIVE zone cannot role change: PASS"
    )


def test_wrong_previous_side_rejected():
    zone = Zone(
        id=4,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
        last_external_price_side=PriceSide.ABOVE,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=108.0,
        extreme_index=20,
        detection_index=21,
    )

    c1, c2, c3 = make_candles()

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is False

    print(
        "Wrong previous price side rejected: PASS"
    )


def test_wrong_reversal_type_rejected():
    zone = Zone(
        id=5,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
        last_external_price_side=PriceSide.BELOW,
    )

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=103.0,
        extreme_index=20,
        detection_index=21,
    )

    c1, c2, c3 = make_candles()

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is False

    print(
        "Wrong reversal type rejected: PASS"
    )


def test_no_pattern_overlap_rejected():
    zone = Zone(
        id=6,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
        last_external_price_side=PriceSide.BELOW,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=95.0,
        extreme_index=20,
        detection_index=21,
    )

    c1 = Candle(
        datetime=datetime(2025, 1, 1, 10, 0),
        open=94.0,
        high=96.0,
        low=92.0,
        close=95.0,
        volume=0,
    )

    c2 = Candle(
        datetime=datetime(2025, 1, 1, 11, 0),
        open=95.0,
        high=97.0,
        low=93.0,
        close=94.0,
        volume=0,
    )

    c3 = Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=94.0,
        high=96.0,
        low=91.0,
        close=92.0,
        volume=0,
    )

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is False

    print(
        "No pattern overlap rejected: PASS"
    )


def test_missing_external_side_rejected():
    zone = Zone(
        id=7,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=108.0,
        extreme_index=20,
        detection_index=21,
    )

    c1, c2, c3 = make_candles()

    assert zone.last_external_price_side is None

    result = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert result is False

    print(
        "Missing external price side rejected: PASS"
    )


def main():
    test_broken_support_to_resistance()
    test_broken_resistance_to_support()
    test_active_zone_cannot_role_change()
    test_wrong_previous_side_rejected()
    test_wrong_reversal_type_rejected()
    test_no_pattern_overlap_rejected()
    test_missing_external_side_rejected()

    print(
        "\nRoleChangeDetector tests: PASS"
    )


if __name__ == "__main__":
    main()