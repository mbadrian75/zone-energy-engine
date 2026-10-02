import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.break_time_calculator import BreakTimeCalculator


def test_normal_persistence():
    break_time, persistence = (
        BreakTimeCalculator.calculate(
            break_index=130,
            interaction_start_index=100,
            previous_movement_time=20,
        )
    )

    assert break_time == 30
    assert persistence == 1.5

    print("Normal persistence: PASS")


def test_bootstrap():
    break_time, persistence = (
        BreakTimeCalculator.calculate(
            break_index=130,
            interaction_start_index=100,
            previous_movement_time=None,
        )
    )

    assert break_time == 30
    assert persistence is None

    print("Bootstrap persistence: PASS")


def test_break_at_origin():
    break_time, persistence = (
        BreakTimeCalculator.calculate(
            break_index=100,
            interaction_start_index=100,
            previous_movement_time=20,
        )
    )

    assert break_time == 0
    assert persistence == 0.0

    print("Break at origin: PASS")


def test_break_before_origin_rejected():
    try:
        BreakTimeCalculator.calculate(
            break_index=99,
            interaction_start_index=100,
            previous_movement_time=20,
        )
    except ValueError:
        print("Break before origin rejected: PASS")
    else:
        raise AssertionError(
            "Break before origin must raise ValueError"
        )


def test_zero_previous_time_rejected():
    try:
        BreakTimeCalculator.calculate(
            break_index=130,
            interaction_start_index=100,
            previous_movement_time=0,
        )
    except ValueError:
        print("Zero previous move time rejected: PASS")
    else:
        raise AssertionError(
            "Zero previous move time must raise ValueError"
        )


def test_negative_previous_time_rejected():
    try:
        BreakTimeCalculator.calculate(
            break_index=130,
            interaction_start_index=100,
            previous_movement_time=-10,
        )
    except ValueError:
        print("Negative previous move time rejected: PASS")
    else:
        raise AssertionError(
            "Negative previous move time must raise ValueError"
        )


def main():
    test_normal_persistence()
    test_bootstrap()
    test_break_at_origin()

    test_break_before_origin_rejected()
    test_zero_previous_time_rejected()
    test_negative_previous_time_rejected()

    print(
        "\nAll BreakTimeCalculator tests: PASS"
    )


if __name__ == "__main__":
    main()