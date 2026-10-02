import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.zone_factory import ZoneFactory
from zone_energy.models import (
    InteractionState,
    Reversal,
    ZoneState,
    ZoneType,
)


def main():
    reversal = Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=2636.298,
        extreme_index=100,
        detection_index=101,
    )

    zone = ZoneFactory.create(
        zone_id=1,
        interaction_id=1,
        reversal=reversal,
        lower_price=2633.655,
        upper_price=2636.298,
        previous_zone_id=None,
    )

    # Zone checks
    assert zone.id == 1
    assert zone.type == ZoneType.RESISTANCE
    assert zone.state == ZoneState.ACTIVE

    assert zone.lower_price == 2633.655
    assert zone.upper_price == 2636.298

    assert zone.creation_extreme == 2636.298
    assert zone.creation_index == 100

    assert zone.created_at_index == 101
    assert zone.previous_zone_id is None

    assert zone.last_interaction_origin_index == 100

    # Initial interaction checks
    assert len(zone.interactions) == 1

    interaction = zone.interactions[0]

    assert interaction.id == 1
    assert interaction.zone_id == 1
    assert interaction.state == InteractionState.OPEN

    assert interaction.start_price == 2636.298
    assert interaction.start_index == 100

    assert interaction.end_price is None
    assert interaction.end_index is None

    assert interaction.distance is None
    assert interaction.movement_time is None

    assert interaction.movement_energy is None
    assert interaction.total_break_evidence is None
    assert interaction.base_energy is None

    # Boundary/height check
    assert zone.height > 0

    print("Zone creation: PASS")
    print("Initial OPEN interaction: PASS")
    print("C2 origin index: PASS")
    print("C3 detection index: PASS")
    print("Initial energy fields: PASS")
    print("Zone height: PASS")

    print("\nAll ZoneFactory tests: PASS")


if __name__ == "__main__":
    main()