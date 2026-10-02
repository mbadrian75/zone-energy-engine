from zone_energy.models import (
    PriceSide,
    Zone,
)


class ZonePriceSideUpdater:
    """
    Updates the last known external price side
    independently for each zone.

    INSIDE does not erase the previous
    external side.
    """

    @staticmethod
    def update(
        zone: Zone,
        current_price_side: PriceSide,
    ) -> None:

        if current_price_side == PriceSide.INSIDE:
            return

        if current_price_side in (
            PriceSide.ABOVE,
            PriceSide.BELOW,
        ):
            zone.last_external_price_side = (
                current_price_side
            )
            return

        raise ValueError(
            f"Unsupported price side: "
            f"{current_price_side}"
        )