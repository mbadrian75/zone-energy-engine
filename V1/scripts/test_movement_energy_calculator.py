import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.interaction_closer import InteractionCloser
from zone_energy.engine.movement_energy_calculator import MovementEnergyCalculator
from zone_energy.engine.previous_move_resolver import PreviousMoveResolver
from zone_energy.models import Interaction, InteractionState, Zone, ZoneState, ZoneType


class MovementEnergyCalculatorTests(unittest.TestCase):
    def test_known_value_and_equal_reference(self):
        self.assertEqual(MovementEnergyCalculator.calculate(60, 5, 30, 10), 4)
        self.assertEqual(MovementEnergyCalculator.calculate(30, 10, 30, 10), 1)

    def test_distance_time_and_scale_relationships(self):
        calculate = MovementEnergyCalculator.calculate
        baseline = calculate(30, 10, 20, 5)
        self.assertEqual(calculate(60, 10, 20, 5), baseline * 2)
        self.assertEqual(calculate(30, 5, 20, 5), baseline * 2)
        self.assertEqual(calculate(300, 100, 200, 50), baseline)

    def test_bootstrap_is_undefined(self):
        self.assertIsNone(MovementEnergyCalculator.calculate(30, 10, None, None))

    def test_partial_reference_is_rejected(self):
        for distance, time in ((None, 10), (30, None)):
            with self.subTest(distance=distance, time=time):
                with self.assertRaises(ValueError):
                    MovementEnergyCalculator.calculate(30, 10, distance, time)

    def test_invalid_inputs_including_bootstrap(self):
        for position in range(4):
            for invalid in (0, -1, float("nan"), float("inf")):
                values = [30, 10, 20, 5]
                values[position] = invalid
                with self.subTest(position=position, invalid=invalid):
                    with self.assertRaises(ValueError):
                        MovementEnergyCalculator.calculate(*values)
        with self.assertRaises(ValueError):
            MovementEnergyCalculator.calculate(0, 10, None, None)

    def test_unrepresentable_result_is_rejected(self):
        with self.assertRaises(ValueError):
            MovementEnergyCalculator.calculate(1e308, 1, 1e-308, 1)

    def test_close_resolve_and_apply(self):
        def zone(zone_id, kind, price, index):
            return Zone(
                id=zone_id, type=kind, state=ZoneState.ACTIVE,
                lower_price=price - 1, upper_price=price + 1,
                creation_extreme=price, creation_index=index,
            )

        previous_origin = zone(1, ZoneType.RESISTANCE, 130, 10)
        origin = zone(2, ZoneType.SUPPORT, 100, 20)
        destination = zone(3, ZoneType.RESISTANCE, 160, 25)
        previous = Interaction(1, 1, InteractionState.OPEN, 130, 10)
        current = Interaction(2, 2, InteractionState.OPEN, 100, 20)
        InteractionCloser.close(previous, previous_origin, origin)
        previous_origin.interactions.append(previous)
        PreviousMoveResolver.resolve(current, origin, [previous_origin, origin])
        InteractionCloser.close(current, origin, destination)
        self.assertEqual(MovementEnergyCalculator.apply(current), 4)
        self.assertEqual(current.movement_energy, 4)
        self.assertIsNone(current.base_energy)
        self.assertIsNone(current.total_break_evidence)

    def test_apply_bootstrap_clears_stale_value(self):
        current = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                              distance=30, movement_time=10, movement_energy=9)
        self.assertIsNone(MovementEnergyCalculator.apply(current))
        self.assertIsNone(current.movement_energy)

    def test_open_or_incomplete_interaction_is_rejected_without_mutation(self):
        for state in (InteractionState.OPEN, InteractionState.CLOSED):
            current = Interaction(1, 1, state, 100, 10, movement_energy=9)
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    MovementEnergyCalculator.apply(current)
                self.assertEqual(current.movement_energy, 9)


if __name__ == "__main__":
    unittest.main()
