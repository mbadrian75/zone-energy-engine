from zone_energy.engine.interaction_starter import (
    InteractionStarter,
)
from zone_energy.engine.role_change_applier import (
    RoleChangeApplier,
)
from zone_energy.engine.role_change_detector import (
    RoleChangeDetector,
)
from zone_energy.models import (
    Candle,
    Interaction,
    Reversal,
    Zone,
)


class RoleChangeProcessor:
    """
    Processes a complete role-change event.

    Detection:
        RoleChangeDetector

    Mutation:
        RoleChangeApplier

    New interaction:
        InteractionStarter
    """

    @staticmethod
    def process(
        zone: Zone,
        reversal: Reversal,
        c1: Candle,
        c2: Candle,
        c3: Candle,
        interaction_id: int,
    ) -> Interaction | None:

        is_role_change = RoleChangeDetector.detect(
            zone=zone,
            reversal=reversal,
            c1=c1,
            c2=c2,
            c3=c3,
        )

        if not is_role_change:
            return None

        RoleChangeApplier.apply(
            zone
        )

        interaction = InteractionStarter.start(
            zone=zone,
            reversal=reversal,
            interaction_id=interaction_id,
        )

        return interaction