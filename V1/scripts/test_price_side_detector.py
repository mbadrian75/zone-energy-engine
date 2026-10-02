import sys
from pathlib import Path

V1_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = V1_ROOT / "src"

sys.path.insert(0, str(SRC_PATH))

from zone_energy.engine.price_side_detector import (
    PriceSideDetector,
)
from zone_energy.models import (
    PriceSide,
    Zone,
    ZoneState,
    ZoneType,
)


def make_zone() -> Zone:
    return Zone(
        id=1,
        type=ZoneType.SUPPORT,
        state=ZoneState.ACTIVE,
        lower_price=100.0,
        upper_price=110.0,
        creation_extreme=100.0,
        creation_index=10,
        created_at_index=11,
    )


def test_price_above_zone():
    zone = make_zone()

    result = PriceSideDetector.detect(
        zone=zone,
        price=115.0,
    )

    assert result == PriceSide.ABOVE

    print("Price above zone: PASS")


def test_price_below_zone():
    zone = make_zone()

    result = PriceSideDetector.detect(
        zone=zone,
        price=95.0,
    )

    assert result == PriceSide.BELOW

    print("Price below zone: PASS")


def test_price_inside_zone():
    zone = make_zone()

    result = PriceSideDetector.detect(
        zone=zone,
        price=105.0,
    )

    assert result == PriceSide.INSIDE

    print("Price inside zone: PASS")


def test_price_on_lower_boundary():
    zone = make_zone()

    result = PriceSideDetector.detect(
        zone=zone,
        price=100.0,
    )

    assert result == PriceSide.INSIDE

    print("Price on lower boundary: PASS")


def test_price_on_upper_boundary():
    zone = make_zone()

    result = PriceSideDetector.detect(
        zone=zone,
        price=110.0,
    )

    assert result == PriceSide.INSIDE

    print("Price on upper boundary: PASS")


def main():
    test_price_above_zone()
    test_price_below_zone()
    test_price_inside_zone()

    test_price_on_lower_boundary()
    test_price_on_upper_boundary()

    print(
        "\nAll PriceSideDetector tests: PASS"
    )


if __name__ == "__main__":
    main()