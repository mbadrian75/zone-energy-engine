import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.interaction_closer import InteractionCloser
from zone_energy.engine.interaction_finalizer import InteractionFinalizer
from zone_energy.models import BreakRecord, Interaction, InteractionState, Zone, ZoneState, ZoneType


def make_zone(zone_id, kind, price, index):
    return Zone(zone_id, kind, ZoneState.ACTIVE, price - 1, price + 1, price, index,
                created_at_index=index + 1)


def scenario(kind=ZoneType.SUPPORT):
    other = ZoneType.RESISTANCE if kind == ZoneType.SUPPORT else ZoneType.SUPPORT
    price = 100 if kind == ZoneType.SUPPORT else 160
    previous_price = 130
    end_price = 160 if kind == ZoneType.SUPPORT else 100
    previous_zone = make_zone(1, other, previous_price, 10)
    origin = make_zone(2, kind, price, 20)
    opposite = make_zone(3, other, end_price, 25)
    previous = Interaction(1, 1, InteractionState.OPEN, previous_price, 10)
    InteractionCloser.close(previous, previous_zone, origin)
    previous_zone.interactions.append(previous)
    current = Interaction(2, 2, InteractionState.OPEN, price, 20,
                          previous_distance=30, previous_movement_time=10)
    origin.interactions.append(current)
    return current, origin, opposite, [previous_zone, origin, opposite]


def break_record(evidence):
    return BreakRecord(9, 23, 140, 3, 2, 1, 2, 4, 1, 0.5, 0.3, evidence)


class InteractionFinalizerTests(unittest.TestCase):
    def test_both_directions_close_and_score(self):
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            with self.subTest(kind=kind):
                current, origin, opposite, history = scenario(kind)
                self.assertIs(InteractionFinalizer.finalize(current, origin, opposite, history, 26), current)
                self.assertEqual(current.state, InteractionState.CLOSED)
                self.assertEqual((current.end_index, current.distance, current.movement_time), (25, 60, 5))
                self.assertEqual((current.movement_energy, current.total_break_evidence, current.base_energy), (4, 0, 4))

    def test_break_evidence_and_snapshots_are_retained(self):
        current, origin, opposite, history = scenario()
        current.breaks.append(break_record(2))
        snapshots = current.breaks
        history_before = deepcopy([history[0], opposite])
        InteractionFinalizer.finalize(current, origin, opposite, iter(history), 26)
        self.assertEqual((current.total_break_evidence, current.base_energy), (2, 6))
        self.assertIs(current.breaks, snapshots)
        self.assertEqual(current.breaks[0], break_record(2))
        self.assertEqual([history[0], opposite], history_before)

    def test_first_move_closes_with_undefined_relative_energy(self):
        current, origin, opposite, history = scenario()
        history = [origin, opposite]
        current.previous_distance = None
        current.previous_movement_time = None
        InteractionFinalizer.finalize(current, origin, opposite, history, 26)
        self.assertEqual(current.state, InteractionState.CLOSED)
        self.assertIsNone(current.movement_energy)
        self.assertIsNone(current.base_energy)
        self.assertEqual(current.total_break_evidence, 0)

    def test_repeated_finalization_does_not_rewrite_history(self):
        current, origin, opposite, history = scenario()
        InteractionFinalizer.finalize(current, origin, opposite, history, 26)
        before = deepcopy(current)
        with self.assertRaises(ValueError):
            InteractionFinalizer.finalize(current, origin, opposite, history, 27)
        self.assertEqual(current, before)

    def test_unconfirmed_opposite_zone_is_rejected(self):
        current, origin, opposite, history = scenario()
        before = deepcopy(current)
        with self.assertRaises(ValueError):
            InteractionFinalizer.finalize(current, origin, opposite, history, 25)
        self.assertEqual(current, before)

    def test_late_calculation_failure_leaves_interaction_open(self):
        current, origin, opposite, history = scenario()
        current.breaks.append(break_record(-1))
        before = deepcopy(current)
        with self.assertRaises(ValueError):
            InteractionFinalizer.finalize(current, origin, opposite, history, 26)
        self.assertEqual(current, before)

    def test_reference_cannot_change_after_break_capture(self):
        current, origin, opposite, history = scenario()
        current.previous_movement_time = 9
        current.breaks.append(break_record(2))
        before = deepcopy(current)
        with self.assertRaises(ValueError):
            InteractionFinalizer.finalize(current, origin, opposite, history, 26)
        self.assertEqual(current, before)

    def test_invalid_histories_do_not_mutate_interaction(self):
        for condition in ("same_type", "future_break", "duplicate", "wrong_owner"):
            current, origin, opposite, history = scenario()
            if condition == "same_type":
                opposite.type = origin.type
            elif condition == "future_break":
                current.breaks.append(replace(break_record(2), break_index=27))
            elif condition == "duplicate":
                history.append(history[0])
            else:
                current.zone_id = 99
            before = deepcopy(current)
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    InteractionFinalizer.finalize(current, origin, opposite, history, 26)
                self.assertEqual(current, before)


if __name__ == "__main__":
    unittest.main()
