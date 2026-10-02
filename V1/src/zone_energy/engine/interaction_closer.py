from zone_energy.models import (
    Interaction,
    InteractionState,
    Zone,
    ZoneType,
)


class InteractionCloser:
    """
    Closes an OPEN interaction when the next
    valid opposite zone is created.

    End point:
        opposite zone creation extreme/index
    """

    @staticmethod
    def close(
        interaction: Interaction,
        origin_zone: Zone,
        opposite_zone: Zone,
    ) -> None:

        if interaction.state != InteractionState.OPEN:
            raise ValueError(
                "Only an OPEN interaction "
                "can be closed"
            )

        if interaction.zone_id != origin_zone.id:
            raise ValueError(
                "Interaction does not belong "
                "to origin_zone"
            )

        if origin_zone.type == opposite_zone.type:
            raise ValueError(
                "Interaction must close on "
                "an opposite zone type"
            )

        if (
            origin_zone.type == ZoneType.SUPPORT
            and opposite_zone.type
            != ZoneType.RESISTANCE
        ):
            raise ValueError(
                "SUPPORT interaction must close "
                "on RESISTANCE"
            )

        if (
            origin_zone.type == ZoneType.RESISTANCE
            and opposite_zone.type
            != ZoneType.SUPPORT
        ):
            raise ValueError(
                "RESISTANCE interaction must close "
                "on SUPPORT"
            )

        end_price = opposite_zone.creation_extreme
        end_index = opposite_zone.creation_index

        movement_time = (
            end_index - interaction.start_index
        )

        if movement_time <= 0:
            raise ValueError(
                "Interaction movement_time "
                "must be greater than zero"
            )

        distance = abs(
            end_price - interaction.start_price
        )

        if distance <= 0:
            raise ValueError(
                "Interaction distance "
                "must be greater than zero"
            )

        interaction.end_price = end_price
        interaction.end_index = end_index

        interaction.distance = distance
        interaction.movement_time = movement_time

        interaction.state = InteractionState.CLOSED