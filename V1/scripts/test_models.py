import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.models import (
    Interaction,
    InteractionState,
    Zone,
    ZoneState,
    ZoneType,
)


def main():
    interaction = Interaction(
        id=1,
        zone_id=1,
        state=InteractionState.OPEN,
        start_price=2600.0,
        start_index=100,
    )

    zone = Zone(
        id=1,
        type=ZoneType.SUPPORT,
        state=ZoneState.ACTIVE,
        lower_price=2598.0,
        upper_price=2602.0,
        creation_extreme=2598.0,
        creation_index=100,
        created_at_index=101,
    )

    zone.interactions.append(interaction)

    print("Valid Zone: OK")
    print("Zone height:", zone.height)
    print("Interaction count:", len(zone.interactions))
    print("Base energy:", interaction.base_energy)

    print("\nTesting invalid zone...")

    try:
        Zone(
            id=2,
            type=ZoneType.RESISTANCE,
            state=ZoneState.ACTIVE,
            lower_price=2605.0,
            upper_price=2600.0,
            creation_extreme=2605.0,
            creation_index=200,
            created_at_index=201,
        )

    except ValueError as error:
        print("Invalid Zone rejected: OK")
        print(error)

    else:
        raise AssertionError(
            "Invalid zone was accepted."
        )


if __name__ == "__main__":
    main()