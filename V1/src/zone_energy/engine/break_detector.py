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
    Break validation is based on candle direction
    and the full candle body being outside the zone.
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
                candle.is_bearish
                and max(
                    candle.open,
                    candle.close,
                ) < zone.lower_price
            )

        if zone.type == ZoneType.RESISTANCE:
            return (
                candle.is_bullish
                and min(
                    candle.open,
                    candle.close,
                ) > zone.upper_price
            )

        raise ValueError(
            f"Unsupported zone type: {zone.type}"
        )