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

        # Attribute the reaction to its C2 extreme, not the pattern's range.
        if not zone.lower_price <= reversal.extreme_price <= zone.upper_price:
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
