from zone_energy.models import (
    Interaction,
    InteractionState,
    Reversal,
    Zone,
)


class InteractionStarter:
    """
    Starts a new OPEN interaction on an existing zone.

    Duplicate interaction origins are rejected.
    """

    @staticmethod
    def start(
        zone: Zone,
        reversal: Reversal,
        interaction_id: int,
    ) -> Interaction | None:
        if interaction_id < 0:
            raise ValueError(
                "interaction_id cannot be negative"
            )

        # Prevent duplicate interaction creation
        # from the same reversal origin (C2).
        if (
            zone.last_interaction_origin_index
            == reversal.extreme_index
        ):
            return None

        interaction = Interaction(
            id=interaction_id,
            zone_id=zone.id,
            state=InteractionState.OPEN,
            start_price=reversal.extreme_price,
            start_index=reversal.extreme_index,
        )

        zone.interactions.append(
            interaction
        )

        zone.last_interaction_origin_index = (
            reversal.extreme_index
        )

        return interaction