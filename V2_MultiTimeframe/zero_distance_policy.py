"""V2-only policy for an opposite reaction with an identical start/end price.

Reject the candidate before finalization; preserve the OPEN interaction and
target zone role. All remaining V1 candle processing, including physical breaks,
still runs. V1 source and its positive-distance/energy invariants are unchanged.
"""
from copy import deepcopy
from collections import Counter
import json

from zone_energy.replay.replay_engine import ReplayEngine

POLICY_VERSION = "reject-zero-distance-v1"
_ACTIVATION_EVENTS = {"reaction_confirmed_by_close", "role_change", "return_reaction"}


class V2ReplayEngine(ReplayEngine):
    def process(self, candle, before_commit=None):
        def key(record):
            return json.dumps(record, sort_keys=True, allow_nan=False)
        previous = Counter(key(record) for record in self.state.rejected_reactions
                           if record.get("policy_version") == POLICY_VERSION)
        events = super().process(candle, before_commit=before_commit)
        recent = []
        # V1 can replay an older reaction window when an origin is invalidated.
        # Compare the final committed histories, so newly rejected historical
        # candidates are audited when they become known at this candle, too.
        for record in self.state.rejected_reactions:
            if record.get("policy_version") != POLICY_VERSION:
                continue
            identity = key(record)
            if previous[identity]:
                previous[identity] -= 1
            else:
                recent.append(deepcopy(record))
        self.recent_policy_rejections = recent
        return events

    def _process_once(self, candle):
        # ReplayEngine stages shallow copies. Allocate new lists on the staged
        # engine, so rejected/failed candles cannot leak into the committed one.
        self._v2_activation_outcomes = []
        self.recent_policy_rejections = []
        events = super()._process_once(candle)
        outcomes = iter(self._v2_activation_outcomes)
        result = []
        for event in events:
            if event in _ACTIVATION_EVENTS:
                try:
                    accepted = next(outcomes)
                except StopIteration as error:
                    raise RuntimeError("V1 activation event contract changed") from error
                result.append(event if accepted else "zero_distance_reaction_rejected")
            else:
                result.append(event)
        if next(outcomes, None) is not None:
            raise RuntimeError("V1 activation event contract changed")
        return result

    def _activate_pending(self, state, departure, index):
        candidate = state.pending_reaction
        current = self._current(state)
        reversal = candidate["reversal"]
        # Do not hide invalid temporal ordering or other V1 validation errors.
        if (current is not None
                and current[1].start_price == reversal["extreme_price"]
                and current[1].start_index < reversal["extreme_index"]
                < reversal["detection_index"] <= index):
            origin, interaction = current
            record = dict(policy_version=POLICY_VERSION, reason="zero_distance",
                zone_id=candidate["zone_id"], origin_zone_id=origin.id,
                interaction_id=interaction.id, role_change=candidate["role_change"],
                reaction_index=reversal["extreme_index"], reaction_type=reversal["type"],
                start_price=interaction.start_price, end_price=reversal["extreme_price"],
                start_index=interaction.start_index, end_index=reversal["extreme_index"],
                movement_time=reversal["extreme_index"] - interaction.start_index,
                distance=0.0, rejected_at=index,
                rejected_datetime=departure.datetime.isoformat())
            self._reject_pending(state, index, "zero_distance")
            state.rejected_reactions[-1].update(record)
            self.recent_policy_rejections.append(deepcopy(record))
            self._v2_activation_outcomes.append(False)
            return
        super()._activate_pending(state, departure, index)
        self._v2_activation_outcomes.append(True)
