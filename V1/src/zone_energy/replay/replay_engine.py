from collections import deque
from copy import copy, deepcopy
from dataclasses import asdict, dataclass, field
from math import isfinite

from zone_energy.config import EngineConfig
from zone_energy.engine.break_detector import BreakDetector
from zone_energy.engine.break_processor import BreakProcessor
from zone_energy.engine.break_record_factory import BreakRecordFactory
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.engine.interaction_finalizer import InteractionFinalizer
from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
from zone_energy.engine.price_side_detector import PriceSideDetector
from zone_energy.engine.return_reversal_detector import ReturnReversalDetector
from zone_energy.engine.return_reversal_processor import ReturnReversalProcessor
from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.engine.role_change_detector import RoleChangeDetector
from zone_energy.engine.role_change_processor import RoleChangeProcessor
from zone_energy.engine.zone_creation_processor import ZoneCreationProcessor
from zone_energy.engine.zone_price_side_updater import ZonePriceSideUpdater
from zone_energy.models import InteractionState, Zone, ZoneState, ZoneType


@dataclass
class ReplayState:
    zones: list
    unattributed_breaks: list
    next_zone_id: int = 1
    next_interaction_id: int = 1
    invalidated_reactions: list = field(default_factory=list)
    pending_c2_breaks: list = field(default_factory=list)
    confirmed_c2_breaks: list = field(default_factory=list)


class _OriginBroken(Exception):
    def __init__(self, zone, interaction, index, candle):
        self.zone = deepcopy(zone)
        self.interaction = deepcopy(interaction)
        self.index = index
        self.candle = candle


class ReplayEngine:
    """Process confirmed candles with at most one OPEN interaction.

    Confirm reactions first, process breaks using one snapshot, then update
    external price sides. Existing-zone reactions close the move at their new
    extreme, not at the zone's original creation point. Ambiguous overlapping
    reaction zones are rejected instead of being selected by iteration order.
    ACTIVE-zone returns take precedence over BROKEN-zone role changes.
    Within either candidate group, the latest creation index takes precedence.
    """

    def __init__(self, config: EngineConfig, year_candles: int, boundary_service):
        InteractionTimeDecayCalculator(config).calculate(0, 0, 0, year_candles)
        self.config = config
        self.year_candles = year_candles
        self.boundary_service = boundary_service
        self.state = ReplayState([], [])
        self.current_index = -1
        self._recent = deque(maxlen=2)
        self._last_datetime = None
        self._breaks = BreakProcessor(config)
        self._snapshots = MarketEnergySnapshotCalculator(config)
        self._break_records = BreakRecordFactory(config)
        self._reaction_seed = None
        self._reaction_window = ()
        self._suppressed = {}

    @staticmethod
    def _current(state):
        candidates = [(zone, move) for zone in state.zones for move in zone.interactions
                      if move.state == InteractionState.OPEN]
        if len(candidates) > 1:
            raise ValueError("Replay history contains multiple OPEN interactions")
        return candidates[0] if candidates else None

    def process(self, candle, before_commit=None):
        """Stage a candle, including any invalidation replay, before checkpointing.

        Retain an immutable seed before each new reaction. If its origin breaks,
        replay that window without that reaction, preserving the zone and scoring
        every intervening break against its corrected historical snapshot.
        """
        staged = copy(self)
        staged._recent = deque(self._recent, maxlen=2)
        previous = self._current(self.state)
        try:
            events = staged._process_once(candle)
        except _OriginBroken as broken:
            if self._reaction_seed is None:
                raise ValueError("Cannot invalidate an origin without its reaction seed") from broken
            staged = copy(self._reaction_seed)
            staged._recent = deque(staged._recent, maxlen=2)
            staged.state = deepcopy(staged.state)
            staged.state.invalidated_reactions = deepcopy(self.state.invalidated_reactions)
            key = (broken.interaction.start_index, broken.zone.type)
            if key in self._suppressed:
                raise ValueError("Previously invalidated reaction became an origin again") from broken
            staged._suppressed = {**self._suppressed, key: broken}
            restored = self._current(staged.state)
            staged.state.invalidated_reactions.append({
                "zone_id": broken.zone.id, "interaction_id": broken.interaction.id,
                "reaction_index": broken.interaction.start_index,
                "reaction_type": broken.zone.type.value,
                "break_index": broken.index,
                "break_datetime": broken.candle.datetime,
                "break_close": broken.candle.close,
                "restored_origin_zone_id": restored[0].id if restored else None,
                "restored_interaction_id": restored[1].id if restored else None,
                "reason": "origin_broken_before_opposite_reaction",
                "invalid_interaction": asdict(broken.interaction),
            })
            events = []
            for bar in self._reaction_window + (candle,):
                events = staged.process(bar)
            events = ["reaction_invalidated", *events]
        else:
            current = self._current(staged.state)
            if current is not None and (previous is None or current[1].id != previous[1].id):
                seed = copy(self)
                seed._recent = deque(self._recent, maxlen=2)
                staged._reaction_seed = seed
                staged._reaction_window = (candle,)
            elif staged._reaction_seed is not None:
                staged._reaction_window = self._reaction_window + (candle,)
        if before_commit is not None:
            before_commit(staged.state, staged.current_index, candle)
        self.__dict__.update(staged.__dict__)
        return events

    def _process_once(self, candle):
        if not all(isfinite(value) for value in (candle.open, candle.high, candle.low, candle.close)):
            raise ValueError("Replay candle prices must be finite")
        if self._last_datetime is not None and candle.datetime <= self._last_datetime:
            raise ValueError("Replay candles must have strictly increasing timestamps")
        index = self.current_index + 1
        pending = deepcopy(self.state)
        current = self._current(pending)
        events = []
        new_reaction = None
        if len(self._recent) == 2:
            c1, c2 = self._recent
            previous_type = current[0].type if current else None
            reversal = ReversalDetector.detect(
                c1, c2, candle, index - 2, index - 1, index,
                previous_type=previous_type,
            )
            suppressed = self._suppressed.get((reversal.extreme_index, reversal.type)) if reversal else None
            if suppressed is not None:
                # Keep the zone, its prior interactions and its role at the break;
                # discard only the provisional reaction and reserve its IDs.
                target = next((zone for zone in pending.zones if zone.id == suppressed.zone.id), None)
                if target is None:
                    target = deepcopy(suppressed.zone)
                    target.interactions = [move for move in target.interactions
                                           if move.id != suppressed.interaction.id]
                    target.last_external_price_side = None
                    pending.zones.append(target)
                target.type = suppressed.zone.type
                target.state = ZoneState.ACTIVE
                target.last_interaction_origin_index = max(
                    (move.start_index for move in target.interactions), default=None)
                pending.next_zone_id = max(pending.next_zone_id, target.id + 1)
                pending.next_interaction_id = max(pending.next_interaction_id, suppressed.interaction.id + 1)
                events.append("invalid_reaction_skipped")
            elif reversal is not None and (current is None or reversal.type != current[0].type):
                matches = []
                for zone in pending.zones:
                    role = RoleChangeDetector.detect(zone, reversal, c1, c2, candle)
                    returned = ReturnReversalDetector.detect(zone, reversal, c1, c2, candle)
                    if role or returned:
                        matches.append((zone, role))
                returns = [(zone, role) for zone, role in matches if not role]
                if returns:
                    matches = returns
                if matches:
                    latest_creation = max(zone.creation_index for zone, _ in matches)
                    matches = [(zone, role) for zone, role in matches
                               if zone.creation_index == latest_creation]
                if len(matches) > 1:
                    details = [
                        "Confirmed reaction overlaps multiple eligible zones",
                        f"Confirmation: index={index}, datetime={candle.datetime.isoformat()}",
                        f"Reaction: type={reversal.type.value}, extreme={reversal.extreme_price}, "
                        f"extreme_index={reversal.extreme_index}",
                    ]
                    for zone, role in matches:
                        contacts = [name for name, bar in (("C1", c1), ("C2", c2), ("C3", candle))
                                    if bar.high >= zone.lower_price and bar.low <= zone.upper_price]
                        details.append(
                            f"Candidate: id={zone.id}, type={zone.type.value}, state={zone.state.value}, "
                            f"range=[{zone.lower_price}, {zone.upper_price}], "
                            f"creation_index={zone.creation_index}, "
                            f"reaction={'role_change' if role else 'return'}, "
                            f"contact={','.join(contacts)}, "
                            f"contains_extreme={zone.lower_price <= reversal.extreme_price <= zone.upper_price}"
                        )
                    raise ValueError("\n".join(details))
                if matches:
                    target, role = matches[0]
                    if current is not None:
                        InteractionFinalizer.finalize(current[1], current[0], target,
                                                     pending.zones, index, ending_reversal=reversal)
                    processor = RoleChangeProcessor if role else ReturnReversalProcessor
                    reaction = processor.process_with_reference(
                        target, reversal, c1, c2, candle, pending.next_interaction_id,
                        index, pending.zones,
                        previous_type=previous_type,
                    )
                    if reaction is not None:
                        new_reaction = (target, reaction)
                        pending.next_interaction_id += 1
                        events.append("role_change" if role else "return_reaction")
                else:
                    boundary = self.boundary_service.resolve(reversal, c2)
                    if boundary is not None:
                        created = ZoneCreationProcessor.process(
                            pending.zones, pending.next_zone_id, pending.next_interaction_id,
                            reversal, *boundary, index,
                            previous_zone_id=current[0].id if current else None,
                        )
                        new_reaction = (created, created.interactions[-1])
                        pending.next_zone_id += 1
                        pending.next_interaction_id += 1
                        events.append("zone_created")
                    else:
                        events.append("missing_boundary")

        if new_reaction is not None:
            if self._confirm_c2_breaks(pending, *new_reaction, c2, index):
                events.append("c2_break_confirmed")
        # A C2 candidate has exactly one chance: the next candle must confirm it.
        pending.pending_c2_breaks = []
        current = self._current(pending)
        if current is not None and BreakDetector.is_broken(current[0], candle):
            raise _OriginBroken(current[0], current[1], index, candle)
        pre_break = self._snapshots.capture(pending.zones, index, self.year_candles)
        aligns = current is not None and (
            (current[0].type == ZoneType.SUPPORT and candle.is_bullish)
            or (current[0].type == ZoneType.RESISTANCE and candle.is_bearish)
        )
        if aligns:
            records = self._breaks.process(current[1], current[0], pending.zones,
                                           candle, index, self.year_candles)
            if records:
                events.append("break")
        # Physical breaks without a confirmed eligible origin remain observable;
        # no origin energy or BreakEvidence is fabricated for these events.
        for zone in pending.zones:
            if BreakDetector.is_broken(zone, candle):
                pending.unattributed_breaks.append({
                    "zone_id": zone.id, "candle_index": index,
                    "close": candle.close, "reason": "no_confirmed_origin",
                })
                energy, median = pre_break.reference_for_break(zone.id)
                pending.pending_c2_breaks.append({
                    "break_index": index, "datetime": candle.datetime,
                    "open": candle.open, "high": candle.high,
                    "low": candle.low, "close": candle.close,
                    "broken_zone_energy_at_break": energy,
                    "median_active_zone_energy_at_break": median,
                    "zone": {"id": zone.id, "type": zone.type.value,
                             "lower_price": zone.lower_price, "upper_price": zone.upper_price,
                             "creation_extreme": zone.creation_extreme,
                             "creation_index": zone.creation_index,
                             "created_at_index": zone.created_at_index},
                })
                zone.state = ZoneState.BROKEN
                events.append("unattributed_break")
            ZonePriceSideUpdater.update(zone, PriceSideDetector.detect(zone, candle.close))
        self._current(pending)
        self.state = pending
        self.current_index = index
        self._last_datetime = candle.datetime
        self._recent.append(candle)
        return events

    def _confirm_c2_breaks(self, state, origin, interaction, c2, confirmation_index):
        """Credit outgoing movement using the immutable old-role C2 references.

        The new origin may have the same zone ID as the broken old role.
        Never use the zone's new role or C3 energies to reconstruct this record.
        """
        aligns = ((origin.type == ZoneType.SUPPORT and c2.is_bullish)
                  or (origin.type == ZoneType.RESISTANCE and c2.is_bearish))
        if not aligns:
            return False
        records, confirmed, keys = [], [], set()
        for saved in state.pending_c2_breaks:
            if saved["break_index"] != interaction.start_index or saved["break_index"] != confirmation_index - 1:
                continue
            if (saved["datetime"], saved["open"], saved["high"], saved["low"], saved["close"]) != (
                    c2.datetime, c2.open, c2.high, c2.low, c2.close):
                raise ValueError("Pending C2 snapshot does not match the confirmed candle")
            values = dict(saved["zone"])
            values["type"] = ZoneType(values["type"])
            old_role = Zone(state=ZoneState.ACTIVE, **values)
            if old_role.type == origin.type or not BreakDetector.is_broken(old_role, c2):
                continue
            key = (old_role.id, saved["break_index"])
            if key in keys or any(
                (record.broken_zone_id, record.break_index) == key
                for zone in state.zones for move in zone.interactions for record in move.breaks
            ):
                raise ValueError("C2 break would be counted more than once")
            record = self._break_records.create(
                old_role, interaction, c2, saved["break_index"],
                saved["broken_zone_energy_at_break"], saved["median_active_zone_energy_at_break"],
            )
            records.append(record)
            keys.add(key)
            confirmed.append({
                "broken_zone_id": old_role.id, "broken_zone_type": old_role.type.value,
                "break_index": record.break_index, "confirmation_index": confirmation_index,
                "origin_zone_id": origin.id, "origin_zone_type": origin.type.value,
                "interaction_id": interaction.id, "same_zone_role_change": old_role.id == origin.id,
                "broken_zone_energy_at_break": record.broken_zone_energy_at_break,
                "median_active_zone_energy_at_break": record.median_active_zone_energy_at_break,
                "break_evidence": record.break_evidence,
            })
        interaction.breaks.extend(records)
        state.confirmed_c2_breaks.extend(confirmed)
        state.unattributed_breaks = [event for event in state.unattributed_breaks
                                    if (event["zone_id"], event["candle_index"]) not in keys]
        return bool(records)
