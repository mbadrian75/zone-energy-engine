from zone_energy.models import (
    PriceSide,
    Zone,
)


class PriceSideDetector:
    """
    Determines the position of a price
    relative to a zone.

    Boundary prices are considered INSIDE.
    """

    @staticmethod
    def detect(
        zone: Zone,
        price: float,
    ) -> PriceSide:

        if price > zone.upper_price:
            return PriceSide.ABOVE

        if price < zone.lower_price:
            return PriceSide.BELOW

        return PriceSide.INSIDE