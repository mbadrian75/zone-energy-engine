import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.return_reversal_processor import (
    ReturnReversalProcessor,
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


def make_zone():
    return Zone(
        id=1,
        type=ZoneType.SUPPORT,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=105.0,
        creation_index=10,
        created_at_index=11,
    )


def make_pattern():
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

    return c1, c2, c3, reversal


def test_valid_return_reversal():
    zone = make_zone()

    original_type = zone.type
    original_state = zone.state
    lower_before = zone.lower_price
    upper_before = zone.upper_price

    c1, c2, c3, reversal = make_pattern()

    interaction = ReturnReversalProcessor.process(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
        interaction_id=100,
    )

    assert interaction is not None

    assert interaction.id == 100
    assert interaction.zone_id == zone.id

    assert (
        interaction.start_price
        == reversal.extreme_price
    )

    assert (
        interaction.start_index
        == reversal.extreme_index
    )

    assert len(zone.interactions) == 1
    assert zone.interactions[0] is interaction

    assert (
        zone.last_interaction_origin_index
        == reversal.extreme_index
    )

    assert zone.type == original_type
    assert zone.state == original_state

    assert zone.lower_price == lower_before
    assert zone.upper_price == upper_before

    print(
        "Valid return + reversal processed: PASS"
    )


def test_duplicate_origin_rejected():
    zone = make_zone()

    c1, c2, c3, reversal = make_pattern()

    first = ReturnReversalProcessor.process(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
        interaction_id=100,
    )

    second = ReturnReversalProcessor.process(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
        interaction_id=101,
    )

    assert first is not None
    assert second is None

    assert len(zone.interactions) == 1
    assert zone.interactions[0].id == 100

    print(
        "Duplicate return interaction rejected: PASS"
    )


def test_invalid_return_no_interaction():
    zone = make_zone()

    original_type = zone.type
    original_state = zone.state

    c1, c2, c3, _ = make_pattern()

    wrong_reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=114.0,
        extreme_index=20,
        detection_index=21,
    )

    interaction = ReturnReversalProcessor.process(
        zone=zone,
        reversal=wrong_reversal,
        c1=c1,
        c2=c2,
        c3=c3,
        interaction_id=100,
    )

    assert interaction is None

    assert len(zone.interactions) == 0

    assert (
        zone.last_interaction_origin_index
        is None
    )

    assert zone.type == original_type
    assert zone.state == original_state

    print(
        "Invalid return causes no interaction: PASS"
    )


def main():
    test_valid_return_reversal()
    test_duplicate_origin_rejected()
    test_invalid_return_no_interaction()

    print(
        "\nReturnReversalProcessor tests: PASS"
    )


if __name__ == "__main__":
    main()