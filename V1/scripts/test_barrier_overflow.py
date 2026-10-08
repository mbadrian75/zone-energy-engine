import sys
import unittest
from math import isfinite,log
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_break_record_factory import make_zone,make_interaction,make_break_candle
from zone_energy.config import EngineConfig
from zone_energy.engine.barrier_calculator import BarrierCalculator,EnergyOverflowError
from zone_energy.engine.break_record_factory import BreakRecordFactory


class BarrierOverflowTests(unittest.TestCase):
    def test_power_and_division_overflow_report_original_inputs(self):
        ratio,cost = BarrierCalculator(EngineConfig()).calculate(1e200,1)
        self.assertTrue(isfinite(cost))
        self.assertAlmostEqual(cost,400*log(10))
        for energy,median in ((1e308,1e-308),):
            with self.assertRaises(EnergyOverflowError) as result:
                BarrierCalculator(EngineConfig()).calculate(energy,median)
            self.assertIn("zone_energy=",str(result.exception))
            self.assertIn("median_active_energy=",str(result.exception))
            self.assertIn("log10_power=",str(result.exception))

    def test_break_context_identifies_candle_zone_and_origin(self):
        with self.assertRaises(EnergyOverflowError) as result:
            BreakRecordFactory(EngineConfig()).create(make_zone(),make_interaction(),
                make_break_candle(),21,1e308,1e-308)
        message = str(result.exception)
        self.assertIn("break_index=21",message)
        self.assertIn("broken_zone_id=7",message)
        self.assertIn("interaction_id=3",message)

    def test_nonfinite_inputs_are_rejected(self):
        for energy,median in ((float("inf"),1),(1,float("nan"))):
            with self.assertRaises(ValueError):
                BarrierCalculator(EngineConfig()).calculate(energy,median)

    def test_original_overflow_values_are_finite_under_new_model(self):
        ratio,cost = BarrierCalculator(EngineConfig()).calculate(5.687846631848622e205,13.315524300732074)
        self.assertTrue(isfinite(ratio) and isfinite(cost))
        self.assertAlmostEqual(cost,942.3586903945397,places=9)
        self.assertEqual(BarrierCalculator(EngineConfig(barrier_cost_transform="power")).calculate(2,1),(2,4))


if __name__ == "__main__":
    unittest.main()
