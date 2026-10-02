import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.zone_price_side_updater import (
    ZonePriceSideUpdater,
)
from zone_energy.models import (
    PriceSide,
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


def test_above_is_stored():
    zone = make_zone()

    assert zone.last_external_price_side is None

    ZonePriceSideUpdater.update(
        zone=zone,
        current_price_side=PriceSide.ABOVE,
    )

    assert (
        zone.last_external_price_side
        == PriceSide.ABOVE
    )

    print(
        "ABOVE is stored: PASS"
    )


def test_below_replaces_above():
    zone = make_zone()

    zone.last_external_price_side = PriceSide.ABOVE

    ZonePriceSideUpdater.update(
        zone=zone,
        current_price_side=PriceSide.BELOW,
    )

    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    print(
        "BELOW replaces ABOVE: PASS"
    )


def test_inside_preserves_previous_side():
    zone = make_zone()

    zone.last_external_price_side = PriceSide.BELOW

    ZonePriceSideUpdater.update(
        zone=zone,
        current_price_side=PriceSide.INSIDE,
    )

    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    print(
        "INSIDE preserves previous side: PASS"
    )


def main():
    test_above_is_stored()
    test_below_replaces_above()
    test_inside_preserves_previous_side()

    print(
        "\nZonePriceSideUpdater tests: PASS"
    )


if __name__ == "__main__":
    main()