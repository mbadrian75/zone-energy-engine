import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.interaction_closer import (
    InteractionCloser,
)
from zone_energy.models import (
    Interaction,
    InteractionState,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone(
    zone_id,
    zone_type,
    creation_extreme,
    creation_index,
):
    return Zone(
        id=zone_id,
        type=zone_type,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=creation_extreme,
        creation_index=creation_index,
        created_at_index=creation_index + 1,
    )


def make_interaction(
    interaction_id,
    zone_id,
    start_price,
    start_index,
):
    return Interaction(
        id=interaction_id,
        zone_id=zone_id,
        state=InteractionState.OPEN,
        start_price=start_price,
        start_index=start_index,
    )


def test_support_to_resistance_close():
    support = make_zone(
        zone_id=1,
        zone_type=ZoneType.SUPPORT,
        creation_extreme=100.0,
        creation_index=10,
    )

    resistance = make_zone(
        zone_id=2,
        zone_type=ZoneType.RESISTANCE,
        creation_extreme=130.0,
        creation_index=20,
    )

    interaction = make_interaction(
        interaction_id=100,
        zone_id=support.id,
        start_price=102.0,
        start_index=12,
    )

    InteractionCloser.close(
        interaction=interaction,
        origin_zone=support,
        opposite_zone=resistance,
    )

    assert (
        interaction.state
        == InteractionState.CLOSED
    )

    assert interaction.end_price == 130.0
    assert interaction.end_index == 20

    assert interaction.distance == 28.0
    assert interaction.movement_time == 8

    print(
        "SUPPORT -> RESISTANCE close: PASS"
    )


def test_resistance_to_support_close():
    resistance = make_zone(
        zone_id=1,
        zone_type=ZoneType.RESISTANCE,
        creation_extreme=130.0,
        creation_index=10,
    )

    support = make_zone(
        zone_id=2,
        zone_type=ZoneType.SUPPORT,
        creation_extreme=100.0,
        creation_index=25,
    )

    interaction = make_interaction(
        interaction_id=100,
        zone_id=resistance.id,
        start_price=128.0,
        start_index=12,
    )

    InteractionCloser.close(
        interaction=interaction,
        origin_zone=resistance,
        opposite_zone=support,
    )

    assert (
        interaction.state
        == InteractionState.CLOSED
    )

    assert interaction.end_price == 100.0
    assert interaction.end_index == 25

    assert interaction.distance == 28.0
    assert interaction.movement_time == 13

    print(
        "RESISTANCE -> SUPPORT close: PASS"
    )


def test_closed_interaction_rejected():
    support = make_zone(
        zone_id=1,
        zone_type=ZoneType.SUPPORT,
        creation_extreme=100.0,
        creation_index=10,
    )

    resistance = make_zone(
        zone_id=2,
        zone_type=ZoneType.RESISTANCE,
        creation_extreme=130.0,
        creation_index=20,
    )

    interaction = make_interaction(
        interaction_id=100,
        zone_id=support.id,
        start_price=102.0,
        start_index=12,
    )

    InteractionCloser.close(
        interaction=interaction,
        origin_zone=support,
        opposite_zone=resistance,
    )

    try:
        InteractionCloser.close(
            interaction=interaction,
            origin_zone=support,
            opposite_zone=resistance,
        )
    except ValueError:
        print(
            "Already CLOSED interaction rejected: PASS"
        )
        return

    raise AssertionError(
        "Expected ValueError for CLOSED interaction"
    )


def test_same_zone_type_rejected():
    support_1 = make_zone(
        zone_id=1,
        zone_type=ZoneType.SUPPORT,
        creation_extreme=100.0,
        creation_index=10,
    )

    support_2 = make_zone(
        zone_id=2,
        zone_type=ZoneType.SUPPORT,
        creation_extreme=90.0,
        creation_index=20,
    )

    interaction = make_interaction(
        interaction_id=100,
        zone_id=support_1.id,
        start_price=102.0,
        start_index=12,
    )

    try:
        InteractionCloser.close(
            interaction=interaction,
            origin_zone=support_1,
            opposite_zone=support_2,
        )
    except ValueError:
        assert (
            interaction.state
            == InteractionState.OPEN
        )

        assert interaction.end_price is None
        assert interaction.end_index is None
        assert interaction.distance is None
        assert interaction.movement_time is None

        print(
            "Same zone type rejected: PASS"
        )
        return

    raise AssertionError(
        "Expected ValueError for same zone type"
    )


def main():
    test_support_to_resistance_close()
    test_resistance_to_support_close()
    test_closed_interaction_rejected()
    test_same_zone_type_rejected()

    print(
        "\nInteractionCloser tests: PASS"
    )


if __name__ == "__main__":
    main()