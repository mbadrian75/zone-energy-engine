from collections.abc import Iterable
from dataclasses import replace

from zone_energy.engine.return_reversal_processor import ReturnReversalProcessor
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
    def process_with_reference(
        zone: Zone,
        reversal: Reversal,
        c1: Candle,
        c2: Candle,
        c3: Candle,
        interaction_id: int,
        current_candle_index: int,
        zones: Iterable[Zone],
    ) -> Interaction | None:
        """Confirm and stage the new role and reaction before changing history."""
        history = list(zones)
        if not any(item is zone for item in history):
            raise ValueError("Zone history must include the supplied zone")
        if not RoleChangeDetector.detect(zone, reversal, c1, c2, c3):
            return None
        pending = replace(zone, interactions=list(zone.interactions))
        RoleChangeApplier.apply(pending)
        pending_history = [pending if item is zone else item for item in history]
        interaction = ReturnReversalProcessor.process_with_reference(
            pending, reversal, c1, c2, c3, interaction_id,
            current_candle_index, pending_history,
        )
        if interaction is None:
            return None
        zone.type = pending.type
        zone.state = pending.state
        zone.interactions.append(interaction)
        zone.last_interaction_origin_index = pending.last_interaction_origin_index
        return interaction

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

        pending = replace(zone, interactions=list(zone.interactions))
        RoleChangeApplier.apply(pending)

        interaction = InteractionStarter.start(
            zone=pending,
            reversal=reversal,
            interaction_id=interaction_id,
        )

        if interaction is None:
            return None
        zone.type = pending.type
        zone.state = pending.state
        zone.interactions.append(interaction)
        zone.last_interaction_origin_index = pending.last_interaction_origin_index
        return interaction
