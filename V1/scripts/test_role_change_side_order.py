import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.price_side_detector import (
    PriceSideDetector,
)
from zone_energy.engine.role_change_detector import (
    RoleChangeDetector,
)
from zone_energy.engine.zone_price_side_updater import (
    ZonePriceSideUpdater,
)
from zone_energy.models import (
    Candle,
    PriceSide,
    Reversal,
    Zone,
    ZoneState,
    ZoneType,
)


def test_role_change_uses_previous_external_side():
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

    c1 = Candle(
        datetime=datetime(2025, 1, 1, 10, 0),
        open=103.0,
        high=106.0,
        low=101.0,
        close=105.0,
        volume=0,
    )

    c2 = Candle(
        datetime=datetime(2025, 1, 1, 11, 0),
        open=105.0,
        high=108.0,
        low=102.0,
        close=104.0,
        volume=0,
    )

    # Current candle closes ABOVE the zone.
    # If its side were updated before role-change
    # detection, BELOW would be overwritten by ABOVE.
    c3 = Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=104.0,
        high=115.0,
        low=103.0,
        close=112.0,
        volume=0,
    )

    # The incoming state must still represent
    # the external side from before the current candle.
    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    role_change = RoleChangeDetector.detect(
        zone=zone,
        reversal=reversal,
        c1=c1,
        c2=c2,
        c3=c3,
    )

    assert role_change is True

    # Role-change detection must not mutate
    # the stored external side.
    assert (
        zone.last_external_price_side
        == PriceSide.BELOW
    )

    # Only after current-candle event processing
    # do we update the side using current close.
    current_side = PriceSideDetector.detect(
        zone,
        c3.close,
    )

    assert current_side == PriceSide.ABOVE

    ZonePriceSideUpdater.update(
        zone,
        current_side,
    )

    assert (
        zone.last_external_price_side
        == PriceSide.ABOVE
    )

    print(
        "Role change uses previous external side: PASS"
    )

    print(
        "Current candle side updates afterward: PASS"
    )


def main():
    test_role_change_uses_previous_external_side()

    print(
        "\nRole change side ordering test: PASS"
    )


if __name__ == "__main__":
    main()