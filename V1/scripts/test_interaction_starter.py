import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.interaction_starter import (
    InteractionStarter,
)
from zone_energy.models import (
    InteractionState,
    Reversal,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone():
    return Zone(
        id=1,
        type=ZoneType.RESISTANCE,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )


def make_reversal():
    return Reversal(
        type=ZoneType.RESISTANCE,
        extreme_price=108.0,
        extreme_index=20,
        detection_index=21,
    )


def test_start_new_interaction():
    zone = make_zone()
    reversal = make_reversal()

    interaction = InteractionStarter.start(
        zone=zone,
        reversal=reversal,
        interaction_id=100,
    )

    assert interaction is not None

    assert interaction.id == 100
    assert interaction.zone_id == zone.id

    assert (
        interaction.state
        == InteractionState.OPEN
    )

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
        "New interaction starts from C2 origin: PASS"
    )


def test_duplicate_origin_rejected():
    zone = make_zone()
    reversal = make_reversal()

    first = InteractionStarter.start(
        zone=zone,
        reversal=reversal,
        interaction_id=100,
    )

    second = InteractionStarter.start(
        zone=zone,
        reversal=reversal,
        interaction_id=101,
    )

    assert first is not None
    assert second is None

    assert len(zone.interactions) == 1

    assert zone.interactions[0].id == 100

    assert (
        zone.last_interaction_origin_index
        == reversal.extreme_index
    )

    print(
        "Duplicate C2 interaction rejected: PASS"
    )


def test_negative_interaction_id_rejected():
    zone = make_zone()
    reversal = make_reversal()

    try:
        InteractionStarter.start(
            zone=zone,
            reversal=reversal,
            interaction_id=-1,
        )
    except ValueError:
        assert len(zone.interactions) == 0
        assert (
            zone.last_interaction_origin_index
            is None
        )

        print(
            "Negative interaction ID rejected: PASS"
        )
        return

    raise AssertionError(
        "Expected ValueError for negative "
        "interaction_id"
    )


def main():
    test_start_new_interaction()
    test_duplicate_origin_rejected()
    test_negative_interaction_id_rejected()

    print(
        "\nInteractionStarter tests: PASS"
    )


if __name__ == "__main__":
    main()