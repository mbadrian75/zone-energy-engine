import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.models import (
    PriceSide,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone(
    zone_id: int,
    zone_type: ZoneType,
) -> Zone:
    return Zone(
        id=zone_id,
        type=zone_type,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )


def test_initial_value_is_none():
    zone = make_zone(
        zone_id=1,
        zone_type=ZoneType.SUPPORT,
    )

    assert zone.last_external_price_side is None

    print(
        "Initial external price side is None: PASS"
    )


def test_zones_keep_independent_side_state():
    zone_a = make_zone(
        zone_id=1,
        zone_type=ZoneType.SUPPORT,
    )

    zone_b = make_zone(
        zone_id=2,
        zone_type=ZoneType.RESISTANCE,
    )

    zone_a.last_external_price_side = PriceSide.ABOVE
    zone_b.last_external_price_side = PriceSide.BELOW

    assert (
        zone_a.last_external_price_side
        == PriceSide.ABOVE
    )

    assert (
        zone_b.last_external_price_side
        == PriceSide.BELOW
    )

    zone_a.last_external_price_side = PriceSide.BELOW

    assert (
        zone_a.last_external_price_side
        == PriceSide.BELOW
    )

    assert (
        zone_b.last_external_price_side
        == PriceSide.BELOW
    )

    print(
        "Zone external price side state is independent: PASS"
    )


def main():
    test_initial_value_is_none()
    test_zones_keep_independent_side_state()

    print(
        "\nZone external price side tests: PASS"
    )


if __name__ == "__main__":
    main()