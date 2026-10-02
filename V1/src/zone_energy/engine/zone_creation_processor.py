from copy import deepcopy
from dataclasses import fields
from math import isfinite

from zone_energy.engine.interaction_finalizer import InteractionFinalizer
from zone_energy.engine.previous_move_resolver import PreviousMoveResolver
from zone_energy.engine.zone_factory import ZoneFactory
from zone_energy.models import Interaction, InteractionState, Reversal, Zone


class ZoneCreationProcessor:
    """Create a confirmed zone, close opposite moves, and initialize its reference.

    Reversal detection and boundary selection are performed by the caller.
    The complete transition is staged before updating the supplied history.
    Existing break snapshots and zone objects retain their identity.
    """

    @staticmethod
    def process(
        zones: list[Zone],
        zone_id: int,
        interaction_id: int,
        reversal: Reversal,
        lower_price: float,
        upper_price: float,
        current_candle_index: int,
        previous_zone_id: int | None = None,
    ) -> Zone:
        for name, value in (
            ("zone_id", zone_id), ("interaction_id", interaction_id),
            ("current_candle_index", current_candle_index),
            ("extreme_index", reversal.extreme_index),
            ("detection_index", reversal.detection_index),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not reversal.extreme_index < reversal.detection_index <= current_candle_index:
            raise ValueError("Reversal must be confirmed after its origin and by the current candle")
        if not all(isfinite(value) for value in (lower_price, upper_price, reversal.extreme_price)):
            raise ValueError("Zone prices must be finite")
        zone_ids = [zone.id for zone in zones]
        if len(set(zone_ids)) != len(zone_ids) or zone_id in zone_ids:
            raise ValueError("Zone IDs must be unique")
        if previous_zone_id is not None and previous_zone_id not in zone_ids:
            raise ValueError("previous_zone_id is absent from history")
        interaction_ids = [move.id for zone in zones for move in zone.interactions]
        if len(set(interaction_ids)) != len(interaction_ids) or interaction_id in interaction_ids:
            raise ValueError("Interaction IDs must be unique")
        for zone in zones:
            if max(zone.creation_index, zone.created_at_index) > current_candle_index:
                raise ValueError("Zone history contains an unconfirmed future zone")
            if zone.creation_index >= reversal.extreme_index:
                raise ValueError("New zones must be processed chronologically")

        pending_history = deepcopy(zones)
        new_zone = ZoneFactory.create(
            zone_id, interaction_id, reversal, lower_price, upper_price, previous_zone_id,
        )
        pending_history.append(new_zone)
        finalized = []
        for zone_position, zone in enumerate(pending_history[:-1]):
            if zone.type == new_zone.type:
                continue
            for move_position, move in enumerate(zone.interactions):
                if move.state == InteractionState.OPEN:
                    InteractionFinalizer.finalize(
                        move, zone, new_zone, pending_history, current_candle_index,
                    )
                    finalized.append((zone_position, move_position, move))
        PreviousMoveResolver.resolve(new_zone.interactions[0], new_zone, pending_history)

        # Commit after every closure and reference calculation has succeeded.
        for zone_position, move_position, pending in finalized:
            original = zones[zone_position].interactions[move_position]
            for field in fields(Interaction):
                if field.name != "breaks":
                    setattr(original, field.name, getattr(pending, field.name))
        zones.append(new_zone)
        return new_zone
