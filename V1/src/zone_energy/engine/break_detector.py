from zone_energy.models import (
    Candle,
    Zone,
    ZoneState,
    ZoneType,
)


class BreakDetector:
    """
    Detects valid V1 zone breaks.

    Wick is ignored.
    Break validation uses the full candle body outside the zone,
    independently of candle color.
    """

    @staticmethod
    def is_broken(
        zone: Zone,
        candle: Candle,
    ) -> bool:

        # Only ACTIVE zones can be broken.
        if zone.state != ZoneState.ACTIVE:
            return False

        if zone.type == ZoneType.SUPPORT:
            return (
                max(
                    candle.open,
                    candle.close,
                ) < zone.lower_price
            )

        if zone.type == ZoneType.RESISTANCE:
            return (
                min(
                    candle.open,
                    candle.close,
                ) > zone.upper_price
            )

        raise ValueError(
            f"Unsupported zone type: {zone.type}"
        )
