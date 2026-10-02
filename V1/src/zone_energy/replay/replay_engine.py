from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from math import isfinite

from zone_energy.config import EngineConfig
from zone_energy.engine.break_detector import BreakDetector
from zone_energy.engine.break_processor import BreakProcessor
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
from zone_energy.models import InteractionState, ZoneState, ZoneType


@dataclass
class ReplayState:
    zones: list
    unattributed_breaks: list
    next_zone_id: int = 1
    next_interaction_id: int = 1


class ReplayEngine:
    """Process confirmed candles with at most one OPEN interaction.

    Confirm reactions first, process breaks using one snapshot, then update
    external price sides. Existing-zone reactions close the move at their new
    extreme, not at the zone's original creation point. Ambiguous overlapping
    reaction zones are rejected instead of being selected by iteration order.
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

    @staticmethod
    def _current(state):
        candidates = [(zone, move) for zone in state.zones for move in zone.interactions
                      if move.state == InteractionState.OPEN]
        if len(candidates) > 1:
            raise ValueError("Replay history contains multiple OPEN interactions")
        return candidates[0] if candidates else None

    def process(self, candle, before_commit=None):
        if not all(isfinite(value) for value in (candle.open, candle.high, candle.low, candle.close)):
            raise ValueError("Replay candle prices must be finite")
        if self._last_datetime is not None and candle.datetime <= self._last_datetime:
            raise ValueError("Replay candles must have strictly increasing timestamps")
        index = self.current_index + 1
        pending = deepcopy(self.state)
        current = self._current(pending)
        events = []
        if len(self._recent) == 2:
            c1, c2 = self._recent
            reversal = ReversalDetector.detect(c1, c2, candle, index - 2, index - 1, index)
            if reversal is not None and (current is None or reversal.type != current[0].type):
                matches = []
                for zone in pending.zones:
                    role = RoleChangeDetector.detect(zone, reversal, c1, c2, candle)
                    returned = ReturnReversalDetector.detect(zone, reversal, c1, c2, candle)
                    if role or returned:
                        matches.append((zone, role))
                if len(matches) > 1:
                    raise ValueError("Confirmed reaction overlaps multiple eligible zones")
                if matches:
                    target, role = matches[0]
                    if current is not None:
                        InteractionFinalizer.finalize(current[1], current[0], target,
                                                     pending.zones, index, ending_reversal=reversal)
                    processor = RoleChangeProcessor if role else ReturnReversalProcessor
                    reaction = processor.process_with_reference(
                        target, reversal, c1, c2, candle, pending.next_interaction_id,
                        index, pending.zones,
                    )
                    if reaction is not None:
                        pending.next_interaction_id += 1
                        events.append("role_change" if role else "return_reaction")
                else:
                    boundary = self.boundary_service.resolve(reversal, c2)
                    if boundary is not None:
                        ZoneCreationProcessor.process(
                            pending.zones, pending.next_zone_id, pending.next_interaction_id,
                            reversal, *boundary, index,
                            previous_zone_id=current[0].id if current else None,
                        )
                        pending.next_zone_id += 1
                        pending.next_interaction_id += 1
                        events.append("zone_created")
                    else:
                        events.append("missing_boundary")

        current = self._current(pending)
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
                zone.state = ZoneState.BROKEN
                events.append("unattributed_break")
            ZonePriceSideUpdater.update(zone, PriceSideDetector.detect(zone, candle.close))
        self._current(pending)
        if before_commit is not None:
            before_commit(pending, index, candle)
        self.state = pending
        self.current_index = index
        self._last_datetime = candle.datetime
        self._recent.append(candle)
        return events
