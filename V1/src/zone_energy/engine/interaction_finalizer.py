from collections.abc import Iterable
from dataclasses import replace

from zone_energy.engine.interaction_base_energy_calculator import InteractionBaseEnergyCalculator
from zone_energy.engine.interaction_closer import InteractionCloser
from zone_energy.engine.movement_energy_calculator import MovementEnergyCalculator
from zone_energy.engine.previous_move_resolver import PreviousMoveResolver
from zone_energy.models import Interaction, InteractionState, Reversal, Zone, ZoneState


class InteractionFinalizer:
    """Close and score a move after its opposite zone has been confirmed.

    Calculations run on a temporary interaction. Historical break snapshots
    are retained, and the original interaction changes only on success.
    The caller selects the next valid opposite zone from confirmed history.
    """

    @staticmethod
    def finalize(
        interaction: Interaction,
        origin_zone: Zone,
        opposite_zone: Zone,
        zones: Iterable[Zone],
        current_candle_index: int,
        ending_reversal: Reversal | None = None,
    ) -> Interaction:
        if isinstance(current_candle_index, bool) or not isinstance(current_candle_index, int):
            raise ValueError("Current candle index must be an integer")
        if interaction.state != InteractionState.OPEN or interaction.base_energy is not None:
            raise ValueError("Only an unfinalized OPEN interaction can be finalized")
        history = list(zones)
        if not any(zone is origin_zone for zone in history):
            raise ValueError("Zone history must include the supplied origin_zone")
        if not any(zone is opposite_zone for zone in history):
            raise ValueError("Zone history must include the supplied opposite_zone")
        if len({zone.id for zone in history}) != len(history):
            raise ValueError("Zone history contains duplicate zone IDs")
        if any(max(zone.creation_index, zone.created_at_index) > current_candle_index for zone in history):
            raise ValueError("Zone history contains an unconfirmed future zone")
        for record in interaction.breaks:
            if not interaction.start_index <= record.break_index <= current_candle_index:
                raise ValueError("Break snapshot lies outside known interaction history")

        endpoint = opposite_zone
        if ending_reversal is not None:
            if not interaction.start_index < ending_reversal.extreme_index < ending_reversal.detection_index <= current_candle_index:
                raise ValueError("Ending reaction must follow the origin and be confirmed")
            if opposite_zone.type != ending_reversal.type and opposite_zone.state != ZoneState.BROKEN:
                raise ValueError("Ending reaction must match the opposite zone's role")
            endpoint = replace(opposite_zone, type=ending_reversal.type,
                               creation_extreme=ending_reversal.extreme_price,
                               creation_index=ending_reversal.extreme_index)
        pending = replace(interaction, breaks=list(interaction.breaks))
        InteractionCloser.close(pending, origin_zone, endpoint)
        PreviousMoveResolver.resolve(pending, origin_zone, history)
        if interaction.breaks and (
            interaction.previous_distance != pending.previous_distance
            or interaction.previous_movement_time != pending.previous_movement_time
        ):
            raise ValueError("Previous move reference differs from captured break evidence")
        MovementEnergyCalculator.apply(pending)
        InteractionBaseEnergyCalculator.apply(pending)

        for name in (
            "state", "end_price", "end_index", "distance", "movement_time",
            "previous_distance", "previous_movement_time", "movement_energy",
            "total_break_evidence", "base_energy",
        ):
            setattr(interaction, name, getattr(pending, name))
        return interaction
