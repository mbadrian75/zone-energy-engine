from zone_energy.engine.interaction_starter import (
    InteractionStarter,
)
from zone_energy.engine.return_reversal_detector import (
    ReturnReversalDetector,
)
from zone_energy.models import (
    Candle,
    Interaction,
    Reversal,
    Zone,
)


class ReturnReversalProcessor:
    """
    Processes a valid Return + Reversal event
    on an existing ACTIVE zone.

    Detection:
        ReturnReversalDetector

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

        is_return_reversal = (
            ReturnReversalDetector.detect(
                zone=zone,
                reversal=reversal,
                c1=c1,
                c2=c2,
                c3=c3,
            )
        )

        if not is_return_reversal:
            return None

        interaction = InteractionStarter.start(
            zone=zone,
            reversal=reversal,
            interaction_id=interaction_id,
        )

        return interaction