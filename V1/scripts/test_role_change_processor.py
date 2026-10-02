import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.role_change_processor import (
    RoleChangeProcessor,
)
from zone_energy.models import (
    Candle,
    PriceSide,
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


def make_broken_support():
    return Zone(
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


def test_valid_role_change():
    zone = make_broken_support()

    lower_before = zone.lower_price
    upper_before = zone.upper_price

    c1 = make_candle(
        "2026-01-01 10:00:00",
        103.0,
        106.0,
        101.0,
        104.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        104.0,
        108.0,
        102.0,
        103.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        103.0,
        105.0,
        99.0,
        100.0,
    )

    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=108.0,
        extreme_index=20,
        detection_index=21,
    )

    interaction = RoleChangeProcessor.process(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
        interaction_id=100,
    )

    assert interaction is not None

    assert zone.type == ZoneType.RESISTANCE
    assert zone.state == ZoneState.ACTIVE

    assert zone.lower_price == lower_before
    assert zone.upper_price == upper_before

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

    print(
        "Valid role change processed: PASS"
    )


def test_invalid_role_change_no_mutation():
    zone = make_broken_support()

    original_type = zone.type
    original_state = zone.state
    original_side = zone.last_external_price_side

    c1 = make_candle(
        "2026-01-01 10:00:00",
        103.0,
        106.0,
        101.0,
        104.0,
    )

    c2 = make_candle(
        "2026-01-01 11:00:00",
        104.0,
        108.0,
        102.0,
        103.0,
    )

    c3 = make_candle(
        "2026-01-01 12:00:00",
        103.0,
        105.0,
        99.0,
        100.0,
    )

    reversal = Reversal(
        type=ZoneType.SUPPORT,
        extreme_price=99.0,
        extreme_index=20,
        detection_index=21,
    )

    interaction = RoleChangeProcessor.process(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
        interaction_id=100,
    )

    assert interaction is None

    assert zone.type == original_type
    assert zone.state == original_state

    assert (
        zone.last_external_price_side
        == original_side
    )

    assert len(zone.interactions) == 0

    assert (
        zone.last_interaction_origin_index
        is None
    )

    print(
        "Invalid role change causes no mutation: PASS"
    )


def main():
    test_valid_role_change()
    test_invalid_role_change_no_mutation()

    print(
        "\nRoleChangeProcessor tests: PASS"
    )


if __name__ == "__main__":
    main()