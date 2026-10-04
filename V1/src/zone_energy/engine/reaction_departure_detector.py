from math import isfinite

from zone_energy.models import Candle, Reversal, Zone, ZoneType


class ReactionDepartureDetector:
    """A reaction requires a close beyond the zone, not a wick excursion."""

    @staticmethod
    def has_departed(zone: Zone, reversal: Reversal, candle: Candle) -> bool:
        if not isfinite(candle.close):
            raise ValueError("Reaction confirmation close must be finite")
        if reversal.type == ZoneType.RESISTANCE:
            return candle.close < zone.lower_price
        if reversal.type == ZoneType.SUPPORT:
            return candle.close > zone.upper_price
        raise ValueError("Unsupported reaction type")
