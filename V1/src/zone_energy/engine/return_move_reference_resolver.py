from collections.abc import Iterable
from math import isfinite

from zone_energy.models import Interaction, InteractionState, Zone


class ReturnMoveReferenceResolver:
    """Use the retained incoming move ending at this confirmed return reaction.

    Its start is the last valid opposite reaction, including returns on old
    zones. Current zone roles and creation extremes cannot replace that
    historical origin. Rejected and invalidated reactions are not retained.
    """

    @staticmethod
    def resolve(
        interaction: Interaction,
        origin_zone: Zone,
        zones: Iterable[Zone],
    ) -> Interaction | None:
        if interaction.zone_id != origin_zone.id:
            raise ValueError("Interaction does not belong to origin_zone")
        if interaction.start_index <= origin_zone.creation_index:
            raise ValueError("Return reaction must follow original zone creation")
        history = list(zones)
        if len({zone.id for zone in history}) != len(history):
            raise ValueError("Zone history contains duplicate IDs")
        candidates = []
        for zone in history:
            for move in zone.interactions:
                if (move is interaction or move.state != InteractionState.CLOSED
                        or move.end_index != interaction.start_index
                        or move.end_price != interaction.start_price):
                    continue
                if move.zone_id != zone.id or move.start_index < zone.creation_index:
                    raise ValueError("Incoming reference does not belong to its zone history")
                distance = abs(move.end_price - move.start_price)
                duration = move.end_index - move.start_index
                if (not isfinite(distance) or distance <= 0 or duration <= 0
                        or move.distance != distance or move.movement_time != duration):
                    raise ValueError("Incoming reference measurements do not match endpoints")
                candidates.append(move)
        source = max(candidates, key=lambda move: move.start_index, default=None)
        if source is None:
            interaction.previous_distance = None
            interaction.previous_movement_time = None
            return None
        if sum(move.start_index == source.start_index for move in candidates) > 1:
            raise ValueError("Last opposite reaction is ambiguous")
        interaction.previous_distance = source.distance
        interaction.previous_movement_time = source.movement_time
        return source
