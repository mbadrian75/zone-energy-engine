from collections.abc import Iterable
from math import isfinite

from zone_energy.models import Interaction, Zone


class ReturnMoveReferenceResolver:
    """Measure the incoming return from the last opposite zone's extreme.

    End price/index are the new reaction's origin extreme/index. Zone states
    do not erase historical reference points. Only zones confirmed by the
    reaction's C3 can participate; later zones never replace this reference.
    """

    @staticmethod
    def resolve(
        interaction: Interaction,
        origin_zone: Zone,
        zones: Iterable[Zone],
    ) -> Zone | None:
        if interaction.zone_id != origin_zone.id:
            raise ValueError("Interaction does not belong to origin_zone")
        if interaction.start_index <= origin_zone.creation_index:
            raise ValueError("Return reaction must follow original zone creation")
        history = list(zones)
        if len({zone.id for zone in history}) != len(history):
            raise ValueError("Zone history contains duplicate IDs")
        candidates = [zone for zone in history if (
            zone.id != origin_zone.id and zone.type != origin_zone.type
            and zone.creation_index < interaction.start_index
            and zone.created_at_index <= interaction.start_index + 1
        )]
        source = max(candidates, key=lambda zone: zone.creation_index, default=None)
        if source is None:
            interaction.previous_distance = None
            interaction.previous_movement_time = None
            return None
        if sum(zone.creation_index == source.creation_index for zone in candidates) > 1:
            raise ValueError("Last opposite zone is ambiguous")
        distance = abs(interaction.start_price - source.creation_extreme)
        duration = interaction.start_index - source.creation_index
        if not isfinite(distance) or distance <= 0 or duration <= 0:
            raise ValueError("Return reference requires positive finite distance and time")
        interaction.previous_distance = distance
        interaction.previous_movement_time = duration
        return source
