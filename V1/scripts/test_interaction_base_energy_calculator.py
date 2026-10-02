import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.interaction_base_energy_calculator import InteractionBaseEnergyCalculator
from zone_energy.models import BreakRecord, Interaction, InteractionState


def record(value):
    return BreakRecord(
        broken_zone_id=3, break_index=15, break_close=120,
        break_time_from_origin=5, broken_zone_energy_at_break=2,
        median_active_zone_energy_at_break=1, barrier_ratio=2,
        barrier_cost=4, displacement=1, displacement_ratio=0.5,
        persistence=1, break_evidence=value,
    )


class InteractionBaseEnergyCalculatorTests(unittest.TestCase):
    def test_evidence_sum_not_break_count(self):
        self.assertEqual(InteractionBaseEnergyCalculator.calculate(4, [1.5, 2.5, 0]), (4, 8))

    def test_no_breaks_and_generator(self):
        self.assertEqual(InteractionBaseEnergyCalculator.calculate(4, []), (0, 4))
        self.assertEqual(InteractionBaseEnergyCalculator.calculate(4, iter([1, 2])), (3, 7))

    def test_bootstrap_and_missing_evidence(self):
        self.assertEqual(InteractionBaseEnergyCalculator.calculate(None, []), (0, None))
        self.assertEqual(InteractionBaseEnergyCalculator.calculate(None, [None]), (None, None))
        self.assertEqual(InteractionBaseEnergyCalculator.calculate(4, [2, None]), (None, None))

    def test_invalid_values_and_overflow(self):
        for invalid in (-1, float("nan"), float("inf")):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    InteractionBaseEnergyCalculator.calculate(4, [None, invalid])
                with self.assertRaises(ValueError):
                    InteractionBaseEnergyCalculator.calculate(invalid, [])
        with self.assertRaises(ValueError):
            InteractionBaseEnergyCalculator.calculate(0, [])
        with self.assertRaises(ValueError):
            InteractionBaseEnergyCalculator.calculate(1e308, [1e308])

    def test_apply_preserves_break_snapshots(self):
        records = [record(1.5), replace(record(2.5), broken_zone_id=4)]
        current = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                              movement_energy=4, breaks=records.copy())
        self.assertEqual(InteractionBaseEnergyCalculator.apply(current), (4, 8))
        self.assertEqual(current.total_break_evidence, 4)
        self.assertEqual(current.base_energy, 8)
        self.assertEqual(current.breaks, records)
        self.assertEqual(current.movement_energy, 4)

    def test_finalized_base_cannot_be_rewritten(self):
        current = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                              movement_energy=4, breaks=[record(2)])
        InteractionBaseEnergyCalculator.apply(current)
        current.breaks.append(record(10))
        with self.assertRaises(ValueError):
            InteractionBaseEnergyCalculator.apply(current)
        self.assertEqual((current.total_break_evidence, current.base_energy), (2, 6))

    def test_open_or_invalid_input_does_not_mutate_totals(self):
        for state, evidence in ((InteractionState.OPEN, 1), (InteractionState.CLOSED, -1)):
            current = Interaction(1, 1, state, 100, 10, movement_energy=4,
                                  total_break_evidence=9, breaks=[record(evidence)])
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    InteractionBaseEnergyCalculator.apply(current)
                self.assertEqual(current.total_break_evidence, 9)
                self.assertIsNone(current.base_energy)

    def test_apply_missing_reference_is_undefined(self):
        current = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                              breaks=[record(None)])
        self.assertEqual(InteractionBaseEnergyCalculator.apply(current), (None, None))


if __name__ == "__main__":
    unittest.main()
