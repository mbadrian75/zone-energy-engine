from math import isfinite
from collections.abc import Iterable
from dataclasses import replace

from zone_energy.engine.previous_move_resolver import PreviousMoveResolver
from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.engine.reaction_departure_detector import ReactionDepartureDetector
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
    """Process valid return reversals on an existing ACTIVE zone."""

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
        *, previous_type=None, departure_candle=None, departure_index=None,
    ) -> Interaction | None:
        """Start a confirmed return and assign its incoming reference atomically."""
        history = list(zones)
        if not any(item is zone for item in history):
            raise ValueError("Zone history must include the supplied zone")
        if len({item.id for item in history}) != len(history):
            raise ValueError("Zone history contains duplicate IDs")
        pending_zone = replace(zone, interactions=list(zone.interactions))
        interaction = ReturnReversalProcessor.process_confirmed(
            pending_zone, reversal, c1, c2, c3, interaction_id, current_candle_index,
            previous_type=previous_type,
            departure_candle=departure_candle, departure_index=departure_index,
        )
        if interaction is None:
            return None
        if any(move.state.value == "open" for item in history for move in item.interactions):
            raise ValueError("Close the current movement before starting another reaction")
        if any(move.id == interaction_id for item in history for move in item.interactions):
            raise ValueError("Interaction ID already exists in market history")
        PreviousMoveResolver.resolve(interaction, zone, history)
        zone.interactions.append(interaction)
        zone.last_interaction_origin_index = pending_zone.last_interaction_origin_index
        return interaction

    @staticmethod
    def process_confirmed(
        zone: Zone,
        reversal: Reversal,
        c1: Candle,
        c2: Candle,
        c3: Candle,
        interaction_id: int,
        current_candle_index: int,
        *, previous_type=None, departure_candle=None, departure_index=None,
    ) -> Interaction | None:
        """Validate C3 confirmation and chronology before starting a reaction.

        Existing interactions retain their origins and energy. Exact replay
        of an already recorded origin returns None without adding evidence.
        Previous-move reference assignment is performed separately.
        """
        for name, value in (
            ("interaction_id", interaction_id),
            ("current_candle_index", current_candle_index),
            ("extreme_index", reversal.extreme_index),
            ("detection_index", reversal.detection_index),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if reversal.extreme_index < 1 or reversal.detection_index != reversal.extreme_index + 1:
            raise ValueError("Reversal must use consecutive C2 and C3 candle indices")
        if reversal.detection_index > current_candle_index:
            raise ValueError("C3 confirmation is not yet available")
        if max(zone.creation_index, zone.created_at_index) > current_candle_index:
            raise ValueError("Zone is not confirmed at the current candle")
        if reversal.extreme_index < zone.creation_index:
            raise ValueError("Reaction starts before the zone exists")
        if not all(isfinite(value) for candle in (c1, c2, c3)
                   for value in (candle.open, candle.high, candle.low, candle.close)):
            raise ValueError("Reversal candle prices must be finite")
        confirmed = ReversalDetector.detect(
            c1, c2, c3, reversal.extreme_index - 1,
            reversal.extreme_index, reversal.detection_index,
            previous_type=previous_type,
        )
        if confirmed != reversal:
            raise ValueError("Supplied reversal does not match the three-candle pattern")
        if departure_candle is None:
            departure_candle, departure_index = c3, reversal.detection_index
        if (not isinstance(departure_index, int) or isinstance(departure_index, bool)
                or not reversal.detection_index <= departure_index <= current_candle_index):
            raise ValueError("Departure must be confirmed within known candle history")
        if not ReactionDepartureDetector.has_departed(zone, reversal, departure_candle):
            return None
        if not ReturnReversalDetector.detect(zone, reversal, c1, c2, c3):
            return None
        if any(move.start_index == reversal.extreme_index for move in zone.interactions):
            return None
        if any(move.id == interaction_id for move in zone.interactions):
            raise ValueError("Interaction ID already exists on this zone")
        last_origin = zone.last_interaction_origin_index
        origins = [move.start_index for move in zone.interactions]
        if last_origin is not None:
            origins.append(last_origin)
        if origins and reversal.extreme_index < max(origins):
            raise ValueError("Reactions must be processed chronologically")
        return ReturnReversalProcessor.process(zone, reversal, c1, c2, c3, interaction_id,
                                             departure_candle=departure_candle)

    @staticmethod
    def process(
        zone: Zone,
        reversal: Reversal,
        c1: Candle,
        c2: Candle,
        c3: Candle,
        interaction_id: int,
        *, departure_candle=None,
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

        if not is_return_reversal or not ReactionDepartureDetector.has_departed(
                zone, reversal, departure_candle or c3):
            return None

        interaction = InteractionStarter.start(
            zone=zone,
            reversal=reversal,
            interaction_id=interaction_id,
        )

        return interaction
