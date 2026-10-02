import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.zone_creation_processor import ZoneCreationProcessor
from zone_energy.models import Interaction, InteractionState, Reversal, ZoneState, ZoneType


def create(history, zone_id, kind, price, index):
    return ZoneCreationProcessor.process(
        history, zone_id, zone_id, Reversal(kind, price, index, index + 1),
        price - 1, price + 1, index + 1,
    )


class ZoneCreationProcessorTests(unittest.TestCase):
    def test_three_zone_lifecycle_and_bootstrap(self):
        history = []
        first = create(history, 1, ZoneType.SUPPORT, 100, 10)
        first_move = first.interactions[0]
        snapshots = first_move.breaks
        self.assertIsNone(first_move.previous_distance)
        second = create(history, 2, ZoneType.RESISTANCE, 130, 20)
        self.assertIs(history[0], first)
        self.assertIs(first.interactions[0], first_move)
        self.assertIs(first_move.breaks, snapshots)
        self.assertEqual(first_move.state, InteractionState.CLOSED)
        self.assertIsNone(first_move.base_energy)
        self.assertEqual((second.interactions[0].previous_distance,
                          second.interactions[0].previous_movement_time), (30, 10))
        third = create(history, 3, ZoneType.SUPPORT, 100, 30)
        self.assertEqual(second.interactions[0].base_energy, 1)
        self.assertEqual(third.interactions[0].state, InteractionState.OPEN)
        self.assertEqual((third.interactions[0].previous_distance,
                          third.interactions[0].previous_movement_time), (30, 10))
        self.assertEqual(len(history), 3)

    def test_same_type_creation_does_not_close_existing_move(self):
        history = []
        first = create(history, 1, ZoneType.SUPPORT, 100, 10)
        with self.assertRaises(ValueError):
            create(history, 2, ZoneType.SUPPORT, 95, 20)
        self.assertEqual(first.interactions[0].state, InteractionState.OPEN)

    def test_multiple_open_moves_are_rejected(self):
        history = []
        origin = create(history, 1, ZoneType.SUPPORT, 100, 10)
        later = Interaction(99, 1, InteractionState.OPEN, 105, 15)
        origin.interactions.append(later)
        before = deepcopy(history)
        with self.assertRaises(ValueError):
            create(history, 2, ZoneType.RESISTANCE, 130, 20)
        self.assertEqual(history, before)

    def test_broken_origin_history_is_preserved(self):
        history = []
        origin = create(history, 1, ZoneType.SUPPORT, 100, 10)
        origin.state = ZoneState.BROKEN
        target = create(history, 2, ZoneType.RESISTANCE, 130, 20)
        self.assertEqual(origin.state, ZoneState.BROKEN)
        self.assertEqual(target.interactions[0].previous_distance, 30)

    def test_late_failure_does_not_close_moves_or_append_zone(self):
        history = []
        origin = create(history, 1, ZoneType.SUPPORT, 100, 10)
        origin.interactions.append(Interaction(99, 1, InteractionState.OPEN, 105, 25))
        before = deepcopy(history)
        with self.assertRaises(ValueError):
            create(history, 2, ZoneType.RESISTANCE, 130, 20)
        self.assertEqual(history, before)

    def test_unconfirmed_zone_and_duplicate_ids_are_rejected(self):
        for condition in ("unconfirmed", "zone_id", "interaction_id", "past"):
            history = []
            create(history, 1, ZoneType.SUPPORT, 100, 10)
            before = deepcopy(history)
            zone_id = 1 if condition == "zone_id" else 2
            move_id = 1 if condition == "interaction_id" else 2
            extreme = 9 if condition == "past" else 20
            now = 20 if condition == "unconfirmed" else 21
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    ZoneCreationProcessor.process(history, zone_id, move_id,
                        Reversal(ZoneType.RESISTANCE, 130, extreme, extreme + 1), 129, 131, now)
                self.assertEqual(history, before)

    def test_ambiguous_incoming_reference_rolls_back_entire_transition(self):
        history = []
        origin = create(history, 1, ZoneType.SUPPORT, 100, 10)
        origin.interactions.append(Interaction(99, 1, InteractionState.OPEN, 101, 10))
        before = deepcopy(history)
        with self.assertRaises(ValueError):
            create(history, 2, ZoneType.RESISTANCE, 130, 20)
        self.assertEqual(history, before)


if __name__ == "__main__":
    unittest.main()
