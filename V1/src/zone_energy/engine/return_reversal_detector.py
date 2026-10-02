from zone_energy.engine.zone_contact_detector import (
    ZoneContactDetector,
)
from zone_energy.models import (
    Candle,
    Reversal,
    Zone,
    ZoneState,
    ZoneType,
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

        has_contact = (
            ZoneContactDetector.has_contact(zone, c1)
            or ZoneContactDetector.has_contact(zone, c2)
            or ZoneContactDetector.has_contact(zone, c3)
        )

        if not has_contact:
            return False

        return True