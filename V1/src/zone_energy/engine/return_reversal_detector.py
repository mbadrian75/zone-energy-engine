from zone_energy.models import (
    Candle,
    Reversal,
    Zone,
    ZoneState,
)


class ReturnReversalDetector:
    """
    Detects a valid Return + Reversal
    on an ACTIVE zone.

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

        if zone.state != ZoneState.ACTIVE:
            return False

        if reversal.type != zone.type:
            return False

        # Candle contact alone does not identify the reacting zone.
        has_contact = zone.lower_price <= reversal.extreme_price <= zone.upper_price

        if not has_contact:
            return False

        return True
