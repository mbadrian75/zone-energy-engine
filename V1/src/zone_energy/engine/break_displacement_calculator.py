from zone_energy.models import (
    Candle,
    Zone,
    ZoneType,
)


class BreakDisplacementCalculator:
    """
    Calculates break displacement and
    displacement ratio for a valid zone break.
    """

    @staticmethod
    def calculate(
        zone: Zone,
        break_candle: Candle,
    ) -> tuple[float, float]:

        zone_height = zone.height

        if zone_height <= 0:
            raise ValueError(
                "zone height must be greater than zero"
            )

        if zone.type == ZoneType.SUPPORT:
            displacement = (
                zone.lower_price
                - break_candle.close
            )

        elif zone.type == ZoneType.RESISTANCE:
            displacement = (
                break_candle.close
                - zone.upper_price
            )

        else:
            raise ValueError(
                f"Unsupported zone type: {zone.type}"
            )

        if displacement < 0:
            raise ValueError(
                "break displacement cannot be negative"
            )

        displacement_ratio = (
            displacement / zone_height
        )

        return (
            displacement,
            displacement_ratio,
        )