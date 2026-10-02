import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.role_change_applier import (
    RoleChangeApplier,
)
from zone_energy.models import (
    Zone,
    ZoneState,
    ZoneType,
)


def test_support_to_resistance():
    zone = Zone(
        id=1,
        type=ZoneType.SUPPORT,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )

    original_lower = zone.lower_price
    original_upper = zone.upper_price

    RoleChangeApplier.apply(zone)

    assert zone.type == ZoneType.RESISTANCE
    assert zone.state == ZoneState.ACTIVE

    assert zone.lower_price == original_lower
    assert zone.upper_price == original_upper

    print(
        "BROKEN SUPPORT -> ACTIVE RESISTANCE: PASS"
    )


def test_resistance_to_support():
    zone = Zone(
        id=2,
        type=ZoneType.RESISTANCE,
        state=ZoneState.BROKEN,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=110.0,
        creation_index=10,
        created_at_index=11,
    )

    original_lower = zone.lower_price
    original_upper = zone.upper_price

    RoleChangeApplier.apply(zone)

    assert zone.type == ZoneType.SUPPORT
    assert zone.state == ZoneState.ACTIVE

    assert zone.lower_price == original_lower
    assert zone.upper_price == original_upper

    print(
        "BROKEN RESISTANCE -> ACTIVE SUPPORT: PASS"
    )


def test_active_zone_rejected():
    zone = Zone(
        id=3,
        type=ZoneType.SUPPORT,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )

    try:
        RoleChangeApplier.apply(zone)
    except ValueError:
        print(
            "ACTIVE zone role change rejected: PASS"
        )
        return

    raise AssertionError(
        "Expected ValueError for ACTIVE zone"
    )


def main():
    test_support_to_resistance()
    test_resistance_to_support()
    test_active_zone_rejected()

    print(
        "\nRoleChangeApplier tests: PASS"
    )


if __name__ == "__main__":
    main()