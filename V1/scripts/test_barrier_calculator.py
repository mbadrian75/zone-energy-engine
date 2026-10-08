import sys
from math import log1p,isclose
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.config import EngineConfig
from zone_energy.engine.barrier_calculator import BarrierCalculator


def test_ratio_equal_one():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    ratio, cost = calculator.calculate(
        zone_energy=10.0,
        median_active_energy=10.0,
    )

    assert ratio == 1.0
    assert isclose(cost, log1p(1))

    print("Barrier ratio = 1: PASS")


def test_ratio_above_one():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    ratio, cost = calculator.calculate(
        zone_energy=20.0,
        median_active_energy=10.0,
    )

    assert ratio == 2.0
    assert isclose(cost, log1p(4))

    print("Barrier ratio > 1: PASS")


def test_ratio_below_one():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    ratio, cost = calculator.calculate(
        zone_energy=5.0,
        median_active_energy=10.0,
    )

    assert ratio == 0.5
    assert isclose(cost, log1p(0.25))

    print("Barrier ratio < 1: PASS")


def test_zero_zone_energy():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    ratio, cost = calculator.calculate(
        zone_energy=0.0,
        median_active_energy=10.0,
    )

    assert ratio == 0.0
    assert cost == 0.0

    print("Zero zone energy: PASS")


def test_zero_median_rejected():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    try:
        calculator.calculate(
            zone_energy=10.0,
            median_active_energy=0.0,
        )
    except ValueError:
        print("Zero median rejected: PASS")
    else:
        raise AssertionError(
            "Zero median must raise ValueError"
        )


def test_negative_median_rejected():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    try:
        calculator.calculate(
            zone_energy=10.0,
            median_active_energy=-5.0,
        )
    except ValueError:
        print("Negative median rejected: PASS")
    else:
        raise AssertionError(
            "Negative median must raise ValueError"
        )


def test_negative_zone_energy_rejected():
    calculator = BarrierCalculator(
        EngineConfig()
    )

    try:
        calculator.calculate(
            zone_energy=-1.0,
            median_active_energy=10.0,
        )
    except ValueError:
        print("Negative zone energy rejected: PASS")
    else:
        raise AssertionError(
            "Negative zone energy must raise ValueError"
        )


def main():
    test_ratio_equal_one()
    test_ratio_above_one()
    test_ratio_below_one()

    test_zero_zone_energy()

    test_zero_median_rejected()
    test_negative_median_rejected()
    test_negative_zone_energy_rejected()

    print(
        "\nAll BarrierCalculator tests: PASS"
    )


if __name__ == "__main__":
    main()
