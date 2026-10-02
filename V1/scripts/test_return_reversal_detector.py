import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.return_reversal_detector import (
    ReturnReversalDetector,
)
from zone_energy.models import (
    Candle,
    Reversal,
    Zone,
    ZoneState,
    ZoneType,
)


def make_candle(
    dt,
    open_price,
    high,
    low,
    close,
):
    return Candle(
        datetime=dt,
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=0,
    )


def make_zone(
    zone_type,
    zone_state=ZoneState.ACTIVE,
):
    return Zone(
        id=1,
        type=zone_type,
        state=zone_state,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=105.0,
        creation_index=10,
        created_at_index=11,
    )


def test_support_return_reversal():
    zone = make_zone(
        ZoneType.SUPPORT
    )

    c1 = make_candle(
        "2026-01-01 10:00:00",
        115.0,
        116.0,
        112.0,
        113.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        113.0,
        114.0,
        105.0,
        106.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        106.0,
        116.0,
        105.0,
        115.0,
    )

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=105.0,
        extreme_index=20,
        detection_index=21,
    )

    assert ReturnReversalDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    print(
        "Support return + reversal detected: PASS"
    )


def test_resistance_return_reversal():
    zone = make_zone(
        ZoneType.RESISTANCE
    )

    c1 = make_candle(
        "2026-01-01 10:00:00",
        95.0,
        98.0,
        94.0,
        97.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        97.0,
        105.0,
        96.0,
        104.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        104.0,
        105.0,
        94.0,
        95.0,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=105.0,
        extreme_index=20,
        detection_index=21,
    )

    assert ReturnReversalDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    print(
        "Resistance return + reversal detected: PASS"
    )


def test_wrong_reversal_type_rejected():
    zone = make_zone(
        ZoneType.SUPPORT
    )

    c1 = make_candle(
        "2026-01-01 10:00:00",
        115.0,
        116.0,
        112.0,
        113.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        113.0,
        114.0,
        105.0,
        106.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        106.0,
        116.0,
        105.0,
        115.0,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=114.0,
        extreme_index=20,
        detection_index=21,
    )

    assert not ReturnReversalDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    print(
        "Wrong reversal type rejected: PASS"
    )


def test_no_contact_rejected():
    zone = make_zone(
        ZoneType.SUPPORT
    )

    c1 = make_candle(
        "2026-01-01 10:00:00",
        120.0,
        125.0,
        118.0,
        122.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        122.0,
        124.0,
        115.0,
        116.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        116.0,
        126.0,
        115.0,
        125.0,
    )

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=115.0,
        extreme_index=20,
        detection_index=21,
    )

    assert not ReturnReversalDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    print(
        "No contact rejected: PASS"
    )


def test_broken_zone_rejected():
    zone = make_zone(
        ZoneType.SUPPORT,
        ZoneState.BROKEN,
    )

    c1 = make_candle(
        "2026-01-01 10:00:00",
        115.0,
        116.0,
        112.0,
        113.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        113.0,
        114.0,
        105.0,
        106.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        106.0,
        116.0,
        105.0,
        115.0,
    )

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=105.0,
        extreme_index=20,
        detection_index=21,
    )

    assert not ReturnReversalDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    print(
        "BROKEN zone rejected: PASS"
    )


def main():
    test_support_return_reversal()
    test_resistance_return_reversal()
    test_wrong_reversal_type_rejected()
    test_no_contact_rejected()
    test_broken_zone_rejected()

    print(
        "\nReturnReversalDetector tests: PASS"
    )


if __name__ == "__main__":
    main()