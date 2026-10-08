import math
import sys
from datetime import datetime
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.config import EngineConfig
from zone_energy.engine.break_record_factory import (
    BreakRecordFactory,
)
from zone_energy.models import (
    Candle,
    Interaction,
    InteractionState,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone() -> Zone:
    return Zone(
        id=7,
        type=ZoneType.RESISTANCE,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=110.0,
        creation_index=10,
        created_at_index=11,
    )


def make_interaction() -> Interaction:
    return Interaction(
        id=3,
        zone_id=7,
        state=InteractionState.OPEN,
        start_price=100.0,
        start_index=20,
        previous_distance=20.0,
        previous_movement_time=10,
    )


def make_break_candle() -> Candle:
    return Candle(
        datetime=datetime(2025, 1, 1, 12, 0),
        open=111.0,
        high=116.0,
        low=110.5,
        close=115.0,
        volume=0.0,
    )


def test_complete_break_record():
    zone = make_zone()
    interaction = make_interaction()
    candle = make_break_candle()

    factory = BreakRecordFactory(
        EngineConfig()
    )

    record = factory.create(
        zone=zone,
        interaction=interaction,
        break_candle=candle,
        break_index=35,
        broken_zone_energy_at_break=20.0,
        median_active_zone_energy_at_break=10.0,
    )

    assert record.broken_zone_id == 7
    assert record.break_index == 35
    assert record.break_close == 115.0

    # 35 - 20
    assert record.break_time_from_origin == 15

    assert record.broken_zone_energy_at_break == 20.0
    assert record.median_active_zone_energy_at_break == 10.0

    # 20 / 10 = 2
    assert record.barrier_ratio == 2.0

    assert math.isclose(record.barrier_cost, math.log1p(4))

    # 115 - 110 = 5
    assert record.displacement == 5.0

    # 5 / 10 = 0.5
    assert record.displacement_ratio == 0.5

    # 15 / 10 = 1.5
    assert record.persistence == 1.5

    expected_break_evidence = (
        math.log1p(4)
        * (
            1.0
            + 1.5
            * math.log1p(0.5)
        )
    )

    assert math.isclose(
        record.break_evidence,
        expected_break_evidence,
    )

    print("Complete BreakRecord: PASS")


def test_factory_does_not_mutate_zone():
    zone = make_zone()
    interaction = make_interaction()
    candle = make_break_candle()

    factory = BreakRecordFactory(
        EngineConfig()
    )

    factory.create(
        zone=zone,
        interaction=interaction,
        break_candle=candle,
        break_index=35,
        broken_zone_energy_at_break=20.0,
        median_active_zone_energy_at_break=10.0,
    )

    assert zone.state == ZoneState.ACTIVE
    assert zone.type == ZoneType.RESISTANCE
    assert zone.lower_price == 100.0
    assert zone.upper_price == 110.0

    print("Zone not mutated: PASS")

def test_bootstrap_break_record():
    zone = make_zone()

    interaction = Interaction(
        id=3,
        zone_id=7,
        state=InteractionState.OPEN,
        start_price=100.0,
        start_index=20,
        previous_distance=None,
        previous_movement_time=None,
    )

    candle = make_break_candle()

    factory = BreakRecordFactory(
        EngineConfig()
    )

    record = factory.create(
        zone=zone,
        interaction=interaction,
        break_candle=candle,
        break_index=35,
        broken_zone_energy_at_break=20.0,
        median_active_zone_energy_at_break=10.0,
    )

    # 35 - 20
    assert record.break_time_from_origin == 15

    # Bootstrap:
    # previous movement time does not exist.
    assert record.persistence is None
    assert record.break_evidence is None

    # Other break measurements still exist.
    assert record.barrier_ratio == 2.0
    assert math.isclose(record.barrier_cost, math.log1p(4))
    assert record.displacement == 5.0
    assert record.displacement_ratio == 0.5

    print("Bootstrap BreakRecord: PASS")

def main():
    test_complete_break_record()
    test_factory_does_not_mutate_zone()
    test_bootstrap_break_record()

    print(
        "\nAll BreakRecordFactory tests: PASS"
    )


if __name__ == "__main__":
    main()
