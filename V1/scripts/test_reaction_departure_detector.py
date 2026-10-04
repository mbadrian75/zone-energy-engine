import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from zone_energy.engine.reaction_departure_detector import ReactionDepartureDetector
from zone_energy.models import Candle, Reversal, Zone, ZoneState, ZoneType


class DepartureTests(unittest.TestCase):
    def test_wicks_and_closes_on_boundary_do_not_confirm_departure(self):
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            zone = Zone(1,kind,ZoneState.ACTIVE,100,110,105,1)
            reversal = Reversal(kind,105,3,4)
            for close in (100,105,110):
                bar = Candle(datetime(2025,1,1),105,120,90,close,0)
                self.assertFalse(ReactionDepartureDetector.has_departed(zone,reversal,bar))
            close = 111 if kind == ZoneType.SUPPORT else 99
            bar = Candle(datetime(2025,1,1),105,120,90,close,0)
            self.assertTrue(ReactionDepartureDetector.has_departed(zone,reversal,bar))

    def test_real_candles_12_13_14_do_not_confirm_resistance_11(self):
        zone = Zone(3,ZoneType.RESISTANCE,ZoneState.ACTIVE,2637.935,2646.098,2646.098,11)
        reversal = Reversal(ZoneType.RESISTANCE,2646.098,11,12)
        for values in [(2642.518,2644.468,2640.064,2641.665),
                       (2641.704,2646.265,2640.148,2643.165),
                       (2643.155,2647.135,2635.865,2642.764)]:
            bar = Candle(datetime(2025,1,2),*values,0)
            self.assertFalse(ReactionDepartureDetector.has_departed(zone,reversal,bar))


if __name__ == "__main__":
    unittest.main()
