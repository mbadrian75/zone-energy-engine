from collections.abc import Iterable
from math import isfinite

from zone_energy.models import Interaction, InteractionState, Zone


class PreviousMoveResolver:
    """Resolve an incoming closed move from an opposite zone.

    Endpoints follow InteractionCloser: the destination zone's
    creation_extreme and creation_index. The caller supplies zone history,
    including broken zones, so historical references remain available.
    Energy calculation is handled separately.
    """

    @staticmethod
    def resolve(
        interaction: Interaction,
        origin_zone: Zone,
        zones: Iterable[Zone],
    ) -> Interaction | None:
        if interaction.zone_id != origin_zone.id:
            raise ValueError("Interaction does not belong to origin_zone")
        if interaction.start_index < origin_zone.creation_index:
            raise ValueError("Interaction starts before origin_zone exists")

        candidates = []
        for zone in zones:
            if zone.id == origin_zone.id or zone.type == origin_zone.type:
                continue
            for move in zone.interactions:
                if move is interaction or move.state != InteractionState.CLOSED:
                    continue
                if (
                    move.end_index != origin_zone.creation_index
                    or move.end_price != origin_zone.creation_extreme
                ):
                    continue
                if move.zone_id != zone.id:
                    raise ValueError("Previous move does not belong to its zone")
                if move.start_index < zone.creation_index:
                    raise ValueError("Previous move starts before its zone exists")
                duration = move.end_index - move.start_index
                distance = abs(move.end_price - move.start_price)
                if duration <= 0 or not isfinite(distance) or distance <= 0:
                    raise ValueError("Previous move must have positive distance and time")
                if move.distance != distance or move.movement_time != duration:
                    raise ValueError("Previous move measurements do not match endpoints")
                candidates.append(move)

        previous = max(candidates, key=lambda move: move.start_index, default=None)
        if previous is not None:
            if sum(move.start_index == previous.start_index for move in candidates) > 1:
                raise ValueError("Ambiguous previous move with the same origin time")

        interaction.previous_distance = previous.distance if previous else None
        interaction.previous_movement_time = previous.movement_time if previous else None
        return previous
