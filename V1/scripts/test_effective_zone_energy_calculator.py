import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.config import EngineConfig
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.models import Interaction, InteractionState, Zone, ZoneState, ZoneType


def make_zone():
    return Zone(1, ZoneType.SUPPORT, ZoneState.ACTIVE, 99, 101, 100, 0,
                created_at_index=1)


def closed(interaction_id, start, energy):
    return Interaction(interaction_id, 1, InteractionState.CLOSED, 100, start,
                       end_price=120, end_index=start + 10, base_energy=energy)


class EffectiveZoneEnergyCalculatorTests(unittest.TestCase):
    def setUp(self):
        self.calculator = EffectiveZoneEnergyCalculator(EngineConfig())

    def test_independent_ages_and_history_preserved(self):
        zone = make_zone()
        zone.interactions = [closed(1, 0, 100), closed(2, 500, 100)]
        snapshot = deepcopy(zone)
        expected = 5 + 100 * (0.05 ** 0.5)
        self.assertAlmostEqual(self.calculator.calculate(zone, 1000, 1000), expected)
        self.assertEqual(zone, snapshot)

    def test_new_reaction_adds_energy_without_resetting_old_age(self):
        zone = make_zone()
        zone.interactions = [closed(1, 0, 100)]
        old_energy = self.calculator.calculate(zone, 1000, 1000)
        zone.interactions.append(closed(2, 990, 20))
        new_energy = self.calculator.calculate(zone, 1000, 1000)
        self.assertAlmostEqual(old_energy, 5)
        self.assertAlmostEqual(new_energy - old_energy, 20 * 0.05 ** 0.01)
        self.assertEqual(zone.interactions[0].base_energy, 100)

    def test_broken_zone_keeps_energy(self):
        zone = make_zone()
        zone.interactions = [closed(1, 0, 100)]
        active = self.calculator.calculate(zone, 1000, 1000)
        zone.state = ZoneState.BROKEN
        self.assertEqual(self.calculator.calculate(zone, 1000, 1000), active)

    def test_empty_and_open_only_have_no_finalized_contribution(self):
        zone = make_zone()
        self.assertIsNone(self.calculator.calculate(zone, 100, 1000))
        zone.interactions = [Interaction(1, 1, InteractionState.OPEN, 100, 50)]
        self.assertIsNone(self.calculator.calculate(zone, 100, 1000))
        zone.interactions.append(closed(2, 0, 100))
        self.assertAlmostEqual(self.calculator.calculate(zone, 1000, 1000), 5)

    def test_undefined_closed_energy_is_not_zero(self):
        zone = make_zone()
        zone.interactions = [closed(1, 0, 100), closed(2, 500, None)]
        self.assertEqual(self.calculator.calculate(zone, 1000, 1000), 5)
        zone.interactions = [closed(2, 500, None)]
        self.assertIsNone(self.calculator.calculate(zone, 1000, 1000))

    def test_defined_zero_remains_zero_with_an_open_reaction(self):
        zone = make_zone()
        zone.interactions = [closed(1,0,0),Interaction(2,1,InteractionState.OPEN,100,50)]
        self.assertEqual(self.calculator.calculate(zone,100,1000),0)

    def test_invalid_empty_zone_time_inputs(self):
        for now, year in ((0, 1000), (100, 0), (100, 2.5), (-1, 1000)):
            with self.subTest(now=now, year=year):
                with self.assertRaises(ValueError):
                    self.calculator.calculate(make_zone(), now, year)

    def test_invalid_snapshot_is_rejected(self):
        for condition in ("owner", "duplicate", "future_origin", "future_end", "nonfinite"):
            zone = make_zone()
            interaction = closed(1, 0, 100)
            zone.interactions = [interaction]
            if condition == "owner":
                interaction.zone_id = 2
            elif condition == "duplicate":
                zone.interactions.append(interaction)
            elif condition == "future_origin":
                interaction.start_index = 101
            elif condition == "future_end":
                interaction.end_index = 101
            elif condition == "nonfinite":
                interaction.base_energy = float("nan")
            with self.subTest(condition=condition):
                with self.assertRaises(ValueError):
                    self.calculator.calculate(zone, 100, 1000)

    def test_overflow_is_rejected(self):
        zone = make_zone()
        zone.interactions = [closed(1, 0, 1.7e308), closed(2, 0, 1.7e308)]
        with self.assertRaises(ValueError):
            self.calculator.calculate(zone, 10, 1000)


if __name__ == "__main__":
    unittest.main()
