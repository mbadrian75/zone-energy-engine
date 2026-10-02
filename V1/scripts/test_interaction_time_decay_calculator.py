import math
import sys
import unittest
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig
from zone_energy.engine.interaction_time_decay_calculator import InteractionTimeDecayCalculator
from zone_energy.models import Interaction, InteractionState


class InteractionTimeDecayCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.calculator = InteractionTimeDecayCalculator(EngineConfig())

    def test_origin_one_and_two_years(self):
        self.assertEqual(self.calculator.calculate(100, 10, 10, 1000), (0, 1, 100))
        age, weight, energy = self.calculator.calculate(100, 10, 1010, 1000)
        self.assertEqual(age, 1000)
        self.assertEqual(weight, 0.05)
        self.assertEqual(energy, 5)
        _, _, energy = self.calculator.calculate(100, 10, 2010, 1000)
        self.assertAlmostEqual(energy, 0.25)

    def test_fractional_year_and_monotonic_decay(self):
        _, weight, energy = self.calculator.calculate(100, 10, 510, 1000)
        self.assertAlmostEqual(weight, math.sqrt(0.05))
        self.assertAlmostEqual(energy, 100 * math.sqrt(0.05))
        self.assertGreater(energy, self.calculator.calculate(100, 10, 1010, 1000)[2])

    def test_market_specific_candle_counts(self):
        first = self.calculator.calculate(100, 0, 1000, 1000)
        second = self.calculator.calculate(100, 0, 200, 200)
        self.assertEqual(first[1:], second[1:])

    def test_configured_weight_and_no_decay(self):
        calculator = InteractionTimeDecayCalculator(EngineConfig(yearly_remaining_weight=0.1))
        self.assertEqual(calculator.calculate(100, 0, 1000, 1000)[2], 10)
        calculator = InteractionTimeDecayCalculator(EngineConfig(yearly_remaining_weight=1))
        self.assertEqual(calculator.calculate(100, 0, 1000, 1000)[2], 100)

    def test_bootstrap_and_zero_base(self):
        self.assertEqual(self.calculator.calculate(None, 0, 1000, 1000), (1000, 0.05, None))
        self.assertEqual(self.calculator.calculate(0, 0, 1000, 1000)[2], 0)

    def test_invalid_configuration(self):
        for value in (0, -1, 1.1, float("nan"), float("inf")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    InteractionTimeDecayCalculator(EngineConfig(yearly_remaining_weight=value))

    def test_invalid_base_and_candle_inputs(self):
        for value in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                self.calculator.calculate(value, 0, 100, 1000)
        for start, now, year in ((-1, 100, 1000), (10, 9, 1000),
                                 (0, 100, 0), (0, 100, -1),
                                 (0, 100, 2.5), (True, 100, 1000),
                                 (0, float("inf"), 1000)):
            with self.subTest(start=start, now=now, year=year):
                with self.assertRaises(ValueError):
                    self.calculator.calculate(100, start, now, year)

    def test_age_is_from_origin_and_history_is_unchanged(self):
        interaction = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                                  end_price=120, end_index=20, distance=20,
                                  movement_time=10, base_energy=100)
        snapshot = replace(interaction)
        self.assertEqual(self.calculator.evaluate(interaction, 1010, 1000), (1000, 0.05, 5))
        self.calculator.evaluate(interaction, 2010, 1000)
        self.assertEqual(interaction, snapshot)

    def test_future_closed_move_cannot_leak_into_past(self):
        interaction = Interaction(1, 1, InteractionState.CLOSED, 100, 10,
                                  end_index=20, base_energy=100)
        with self.assertRaises(ValueError):
            self.calculator.evaluate(interaction, 15, 1000)

    def test_open_or_missing_end_is_rejected(self):
        for state, end in ((InteractionState.OPEN, 20), (InteractionState.CLOSED, None)):
            interaction = Interaction(1, 1, state, 100, 10, end_index=end)
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    self.calculator.evaluate(interaction, 100, 1000)


if __name__ == "__main__":
    unittest.main()
