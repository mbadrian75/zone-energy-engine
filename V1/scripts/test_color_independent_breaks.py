import sys
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_outgoing_c2_breaks import fixture
from test_replay_engine import Boundary
from zone_energy.config import EngineConfig
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


class ColorIndependentBreakTests(unittest.TestCase):
    def test_real_c28_bullish_break_belongs_to_resistance_origin(self):
        engine = ReplayEngine(EngineConfig(),5905,Boundary())
        origin = Zone(7,ZoneType.RESISTANCE,ZoneState.ACTIVE,2662.785,2665.185,2665.185,27,
                      created_at_index=28)
        origin.interactions = [Interaction(5,7,InteractionState.OPEN,2665.185,27)]
        target = Zone(4,ZoneType.RESISTANCE,ZoneState.ACTIVE,2657.914,2660.374,2660.374,18,
                      created_at_index=19)
        engine.state.zones = [target,origin]
        engine.current_index = 27
        candle = Candle(datetime(2025,1,2,23),2662.125,2664.195,2661.585,2662.735,0)
        engine.process(candle)
        self.assertEqual(engine.state.unattributed_breaks,[])
        self.assertEqual(target.state,ZoneState.ACTIVE)  # Staging does not mutate caller objects.
        current = engine._current(engine.state)[1]
        self.assertEqual([(record.broken_zone_id,record.break_index) for record in current.breaks],[(4,28)])

    def test_bearish_c2_can_start_support_and_credit_resistance_break(self):
        engine,bars,snapshot = fixture()
        c2 = replace(bars[2],open=2665)
        self.assertTrue(c2.is_bearish)
        engine.process(c2)
        engine.process(bars[3])
        zone,move = engine._current(engine.state)
        self.assertEqual(zone.type,ZoneType.SUPPORT)
        self.assertEqual(move.breaks[0].broken_zone_id,19)
        energy,median = snapshot.reference_for_break(19)
        self.assertEqual(move.breaks[0].broken_zone_energy_at_break,energy)
        self.assertEqual(move.breaks[0].median_active_zone_energy_at_break,median)


if __name__ == "__main__":
    unittest.main()
