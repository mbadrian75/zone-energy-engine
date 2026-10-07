import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from test_break_record_factory import make_zone,make_interaction,make_break_candle
from zone_energy.config import EngineConfig
from zone_energy.engine.barrier_calculator import BarrierCalculator,EnergyOverflowError
from zone_energy.engine.break_record_factory import BreakRecordFactory


class BarrierOverflowTests(unittest.TestCase):
    def test_power_and_division_overflow_report_original_inputs(self):
        for energy,median in ((1e200,1),(1e308,1e-308)):
            with self.assertRaises(EnergyOverflowError) as result:
                BarrierCalculator(EngineConfig()).calculate(energy,median)
            self.assertIn("zone_energy=",str(result.exception))
            self.assertIn("median_active_energy=",str(result.exception))
            self.assertIn("log10_barrier_cost=",str(result.exception))

    def test_break_context_identifies_candle_zone_and_origin(self):
        with self.assertRaises(EnergyOverflowError) as result:
            BreakRecordFactory(EngineConfig()).create(make_zone(),make_interaction(),
                make_break_candle(),21,1e200,1)
        message = str(result.exception)
        self.assertIn("break_index=21",message)
        self.assertIn("broken_zone_id=7",message)
        self.assertIn("interaction_id=3",message)

    def test_nonfinite_inputs_are_rejected(self):
        for energy,median in ((float("inf"),1),(1,float("nan"))):
            with self.assertRaises(ValueError):
                BarrierCalculator(EngineConfig()).calculate(energy,median)


if __name__ == "__main__":
    unittest.main()
