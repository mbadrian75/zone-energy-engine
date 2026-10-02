from zone_energy.models import (
    Candle,
    PriceSide,
    Reversal,
    Zone,
    ZoneState,
    ZoneType,
)


class RoleChangeDetector:
    """
    Detects whether a BROKEN zone satisfies
    the V1 conditions for a role change.

    This detector does not mutate the zone.
    """

    @staticmethod
    def detect(
        zone: Zone,
        reversal: Reversal,
        c1: Candle,
        c2: Candle,
        c3: Candle,
    ) -> bool:
        # Role change is only possible
        # for a BROKEN zone.
        if zone.state != ZoneState.BROKEN:
            return False

        pattern_high = max(
            c1.high,
            c2.high,
            c3.high,
        )

        pattern_low = min(
            c1.low,
            c2.low,
            c3.low,
        )

        # The full three-candle reversal pattern
        # must overlap the zone.
        has_pattern_overlap = (
            pattern_high >= zone.lower_price
            and pattern_low <= zone.upper_price
        )

        if not has_pattern_overlap:
            return False

        # Broken SUPPORT:
        # price must have approached from below,
        # then form a RESISTANCE reversal.
        if zone.type == ZoneType.SUPPORT:
            return (
                zone.last_external_price_side
                == PriceSide.BELOW
                and reversal.type
                == ZoneType.RESISTANCE
            )

        # Broken RESISTANCE:
        # price must have approached from above,
        # then form a SUPPORT reversal.
        if zone.type == ZoneType.RESISTANCE:
            return (
                zone.last_external_price_side
                == PriceSide.ABOVE
                and reversal.type
                == ZoneType.SUPPORT
            )

        raise ValueError(
            f"Unsupported zone type: {zone.type}"
        )