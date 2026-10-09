import sys
import unittest
import math
from copy import deepcopy
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.interaction_finalizer import InteractionFinalizer
from zone_energy.config import EngineConfig
from zone_energy.engine.break_processor import BreakProcessor
from zone_energy.engine.previous_move_resolver import PreviousMoveResolver
from zone_energy.engine.return_reversal_processor import ReturnReversalProcessor
from zone_energy.models import Interaction, InteractionState, Reversal, Zone, ZoneState, ZoneType
from zone_energy.models import Candle


def make_zone(zone_id, kind, price, index):
    return Zone(zone_id, kind, ZoneState.ACTIVE, price - 1, price + 1, price, index,
                created_at_index=index + 1)


def incoming(source, price, index, start_price=None, start_index=None, identifier=900):
    start_price = source.creation_extreme if start_price is None else start_price
    start_index = source.creation_index if start_index is None else start_index
    move = Interaction(identifier, source.id, InteractionState.CLOSED, start_price, start_index,
        end_price=price, end_index=index, distance=abs(price-start_price),
        movement_time=index-start_index)
    source.interactions.append(move)
    return move


def return_case():
    origin = make_zone(1, ZoneType.SUPPORT, 100, 10)
    old = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                      end_index=15, base_energy=5)
    origin.interactions.append(old)
    origin.last_interaction_origin_index = 10
    opposite = make_zone(2, ZoneType.RESISTANCE, 130, 20)
    incoming(opposite, 100, 30)
    c1 = Candle(datetime(2025, 1, 1, 10), 110, 115, 105, 108, 0)
    c2 = Candle(datetime(2025, 1, 1, 11), 108, 112, 100, 101, 0)
    c3 = Candle(datetime(2025, 1, 1, 12), 101, 114, 101, 110, 0)
    reversal = Reversal(ZoneType.SUPPORT, 100, 30, 31)
    return origin, opposite, reversal, c1, c2, c3


class ReturnMoveReferenceTests(unittest.TestCase):
    def test_actual_986_uses_latest_return_on_old_opposite_zone(self):
        origin = make_zone(304, ZoneType.SUPPORT, 3387.798, 2733)
        stale = make_zone(333, ZoneType.RESISTANCE, 3379.798, 3523)
        source = make_zone(263, ZoneType.RESISTANCE, 3300, 2600)
        reference = incoming(source, 3380.035, 3565, 3403.925, 3561, 985)
        current = Interaction(986, 304, InteractionState.OPEN, 3380.035, 3565)
        self.assertIs(PreviousMoveResolver.resolve(current, origin, [origin, stale, source]), reference)
        self.assertAlmostEqual(current.previous_distance, 23.890)
        self.assertEqual(current.previous_movement_time, 4)
        from zone_energy.engine.movement_energy_calculator import MovementEnergyCalculator
        current.state = InteractionState.CLOSED
        current.distance, current.movement_time = 21.494, 1
        MovementEnergyCalculator.apply(current)
        self.assertAlmostEqual(current.movement_energy, 3.59882796149016)
        source.type = ZoneType.SUPPORT
        self.assertIs(PreviousMoveResolver.resolve(current, origin, [origin, source]), reference)

    def test_zone_creation_without_valid_incoming_reaction_is_not_reference(self):
        origin = make_zone(304, ZoneType.SUPPORT, 3387.798, 2733)
        stale = make_zone(333, ZoneType.RESISTANCE, 3379.798, 3523)
        current = Interaction(986, 304, InteractionState.OPEN, 3380.035, 3565)
        self.assertIsNone(PreviousMoveResolver.resolve(current, origin, [origin, stale]))
        self.assertIsNone(current.previous_distance)

    def test_return_reference_in_both_directions(self):
        for kind, source_kind, source_price, target_price in (
            (ZoneType.SUPPORT, ZoneType.RESISTANCE, 130, 100),
            (ZoneType.RESISTANCE, ZoneType.SUPPORT, 100, 130),
        ):
            origin = make_zone(1, kind, target_price, 10)
            source = make_zone(2, source_kind, source_price, 20)
            reference = incoming(source, target_price, 30)
            current = Interaction(3, 1, InteractionState.OPEN, target_price, 30)
            self.assertIs(PreviousMoveResolver.resolve(current, origin, [origin, source]), source.interactions[0])
            self.assertEqual((current.previous_distance, current.previous_movement_time), (30, 10))

    def test_latest_opposite_zone_and_new_reaction_extreme(self):
        origin, source, *_ = return_case()
        older = make_zone(3, ZoneType.RESISTANCE, 140, 15)
        same_type = make_zone(4, ZoneType.SUPPORT, 95, 25)
        source.interactions.clear()
        incoming(source, 102, 30)
        current = Interaction(5, 1, InteractionState.OPEN, 102, 30)
        self.assertIs(PreviousMoveResolver.resolve(current, origin, [older, same_type, source]), source.interactions[0])
        self.assertEqual((current.previous_distance, current.previous_movement_time), (28, 10))

    def test_future_and_late_confirmed_zones_do_not_replace_reference(self):
        origin, source, *_ = return_case()
        future = make_zone(3, ZoneType.RESISTANCE, 160, 35)
        late = make_zone(4, ZoneType.RESISTANCE, 140, 29)
        late.created_at_index = 32
        current = Interaction(5, 1, InteractionState.OPEN, 100, 30)
        self.assertIs(PreviousMoveResolver.resolve(current, origin, [source, future, late]), source.interactions[0])

    def test_broken_source_remains_historical_reference(self):
        origin, source, *_ = return_case()
        source.state = ZoneState.BROKEN
        current = Interaction(3, 1, InteractionState.OPEN, 100, 30)
        PreviousMoveResolver.resolve(current, origin, [source])
        self.assertEqual(current.previous_distance, 30)
        self.assertEqual(source.state, ZoneState.BROKEN)

    def test_start_assigns_reference_without_changing_old_reaction(self):
        origin, source, reversal, c1, c2, c3 = return_case()
        before = deepcopy(origin.interactions[0])
        current = ReturnReversalProcessor.process_with_reference(
            origin, reversal, c1, c2, c3, 3, 31, [origin, source],
        )
        self.assertEqual((current.previous_distance, current.previous_movement_time), (30, 10))
        self.assertEqual(origin.interactions[0], before)
        self.assertIsNone(ReturnReversalProcessor.process_with_reference(
            origin, reversal, c1, c2, c3, 4, 31, [origin, source],
        ))
        self.assertEqual(len(origin.interactions), 2)

    def test_return_can_finalize_using_same_reference(self):
        origin, source, reversal, c1, c2, c3 = return_case()
        history = [origin, source]
        current = ReturnReversalProcessor.process_with_reference(
            origin, reversal, c1, c2, c3, 3, 31, history,
        )
        destination = make_zone(4, ZoneType.RESISTANCE, 160, 35)
        history.append(destination)
        InteractionFinalizer.finalize(current, origin, destination, history, 36)
        self.assertEqual((current.previous_distance, current.previous_movement_time), (30, 10))
        self.assertEqual(current.movement_energy, 4)
        self.assertEqual(current.base_energy, 4)

    def test_missing_source_stays_undefined(self):
        origin, _, reversal, c1, c2, c3 = return_case()
        current = ReturnReversalProcessor.process_with_reference(
            origin, reversal, c1, c2, c3, 3, 31, [origin],
        )
        self.assertEqual((current.previous_distance, current.previous_movement_time), (None, None))

    def test_start_break_and_finalize_keep_one_reference(self):
        origin, source, reversal, c1, c2, c3 = return_case()
        source.interactions.append(Interaction(2, 2, InteractionState.CLOSED, 130, 20,
                                              end_index=25, base_energy=20))
        barrier = make_zone(5, ZoneType.RESISTANCE, 110, 15)
        barrier.interactions.append(Interaction(5, 5, InteractionState.CLOSED, 110, 15,
                                               end_index=16, base_energy=10))
        history = [origin, source, barrier]
        current = ReturnReversalProcessor.process_with_reference(
            origin, reversal, c1, c2, c3, 3, 31, history,
        )
        break_candle = Candle(datetime(2025, 1, 1, 13), 112, 116, 112, 115, 0)
        records = BreakProcessor(EngineConfig()).process(current, origin, history,
                                                        break_candle, 32, 1000)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].persistence, 0.2)
        self.assertAlmostEqual(records[0].break_evidence, math.log1p(1) * (1 + 0.2 * math.log1p(2)))
        destination = make_zone(4, ZoneType.RESISTANCE, 160, 35)
        history.append(destination)
        InteractionFinalizer.finalize(current, origin, destination, history, 36)
        self.assertEqual(current.previous_movement_time, 10)
        self.assertAlmostEqual(current.base_energy, 4 + math.log1p(1) * (1 + 0.2 * math.log1p(2)))

    def test_invalid_reference_does_not_append_reaction(self):
        origin, source, reversal, c1, c2, c3 = return_case()
        source.interactions[0].distance = 0
        before = deepcopy(origin)
        with self.assertRaises(ValueError):
            ReturnReversalProcessor.process_with_reference(origin, reversal, c1, c2, c3, 3, 31, [origin, source])
        self.assertEqual(origin, before)


if __name__ == "__main__":
    unittest.main()
