from zone_energy.models import (
    Candle,
    Zone,
)


class ZoneContactDetector:
    """
    Detects whether a candle range overlaps
    the price range of a zone.

    Contact alone does not create an interaction.
    """

    @staticmethod
    def has_contact(
        zone: Zone,
        candle: Candle,
    ) -> bool:

        return (
            candle.high >= zone.lower_price
            and candle.low <= zone.upper_price
        )