import math
import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.break_evidence_calculator import (
    BreakEvidenceCalculator,
)


def test_normal_break_evidence():
    displacement_evidence, break_evidence = (
        BreakEvidenceCalculator.calculate(
            barrier_cost=4.0,
            persistence=1.5,
            displacement_ratio=0.5,
        )
    )

    expected_displacement_evidence = math.log1p(
        0.5
    )

    expected_break_evidence = (
        4.0
        * (
            1.0
            + 1.5
            * expected_displacement_evidence
        )
    )

    assert math.isclose(
        displacement_evidence,
        expected_displacement_evidence,
    )

    assert math.isclose(
        break_evidence,
        expected_break_evidence,
    )

    print("Normal break evidence: PASS")


def test_zero_barrier_cost():
    displacement_evidence, break_evidence = (
        BreakEvidenceCalculator.calculate(
            barrier_cost=0.0,
            persistence=2.0,
            displacement_ratio=1.0,
        )
    )

    assert math.isclose(
        displacement_evidence,
        math.log1p(1.0),
    )

    assert break_evidence == 0.0

    print("Zero barrier cost: PASS")


def test_bootstrap():
    displacement_evidence, break_evidence = (
        BreakEvidenceCalculator.calculate(
            barrier_cost=4.0,
            persistence=None,
            displacement_ratio=0.5,
        )
    )

    assert math.isclose(
        displacement_evidence,
        math.log1p(0.5),
    )

    assert break_evidence is None

    print("Bootstrap break evidence: PASS")


def test_zero_displacement_ratio():
    displacement_evidence, break_evidence = (
        BreakEvidenceCalculator.calculate(
            barrier_cost=4.0,
            persistence=1.5,
            displacement_ratio=0.0,
        )
    )

    assert displacement_evidence == 0.0
    assert break_evidence == 4.0

    print("Zero displacement ratio: PASS")


def test_negative_barrier_rejected():
    try:
        BreakEvidenceCalculator.calculate(
            barrier_cost=-1.0,
            persistence=1.0,
            displacement_ratio=0.5,
        )
    except ValueError:
        print("Negative barrier cost rejected: PASS")
    else:
        raise AssertionError(
            "Negative barrier cost must raise ValueError"
        )


def test_negative_persistence_rejected():
    try:
        BreakEvidenceCalculator.calculate(
            barrier_cost=1.0,
            persistence=-1.0,
            displacement_ratio=0.5,
        )
    except ValueError:
        print("Negative persistence rejected: PASS")
    else:
        raise AssertionError(
            "Negative persistence must raise ValueError"
        )


def test_negative_displacement_ratio_rejected():
    try:
        BreakEvidenceCalculator.calculate(
            barrier_cost=1.0,
            persistence=1.0,
            displacement_ratio=-0.5,
        )
    except ValueError:
        print(
            "Negative displacement ratio rejected: PASS"
        )
    else:
        raise AssertionError(
            "Negative displacement ratio must raise ValueError"
        )


def main():
    test_normal_break_evidence()
    test_zero_barrier_cost()
    test_bootstrap()
    test_zero_displacement_ratio()

    test_negative_barrier_rejected()
    test_negative_persistence_rejected()
    test_negative_displacement_ratio_rejected()

    print(
        "\nAll BreakEvidenceCalculator tests: PASS"
    )


if __name__ == "__main__":
    main()