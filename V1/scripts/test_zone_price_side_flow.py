import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.price_side_detector import (
    PriceSideDetector,
)
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


def process_close(
    zone: Zone,
    close_price: float,
) -> PriceSide:
    current_side = PriceSideDetector.detect(
        zone=zone,
        price=close_price,
    )

    ZonePriceSideUpdater.update(
        zone=zone,
        current_price_side=current_side,
    )

    return current_side


def main():
    zone = make_zone()

    assert zone.last_external_price_side is None

    # Price is below the zone.
    side = process_close(
        zone=zone,
        close_price=95.0,
    )

    assert side == PriceSide.BELOW
    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    print(
        "95 -> BELOW -> stored BELOW: PASS"
    )

    # Price enters the zone.
    side = process_close(
        zone=zone,
        close_price=102.0,
    )

    assert side == PriceSide.INSIDE
    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    print(
        "102 -> INSIDE -> preserves BELOW: PASS"
    )

    # Price remains inside the zone.
    side = process_close(
        zone=zone,
        close_price=108.0,
    )

    assert side == PriceSide.INSIDE
    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    print(
        "108 -> INSIDE -> preserves BELOW: PASS"
    )

    # Price exits above the zone.
    side = process_close(
        zone=zone,
        close_price=115.0,
    )

    assert side == PriceSide.ABOVE
    assert (
        zone.last_external_price_side
        == PriceSide.ABOVE
    )

    print(
        "115 -> ABOVE -> stored ABOVE: PASS"
    )

    print(
        "\nZone price side flow tests: PASS"
    )


if __name__ == "__main__":
    main()