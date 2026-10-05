import sys
import unittest
from datetime import datetime,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from zone_energy.config import EngineConfig
from zone_energy.models import Candle,Interaction,InteractionState,Zone,ZoneState,ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


class RestoredOriginAuditTests(unittest.TestCase):
    def test_same_candle_confirmations_report_actual_restored_support375(self):
        prices = [(2772.238,2774.815,2770.365,2771.825),
                  (2771.805,2776.485,2771.805,2775.045),
                  (2775.005,2778.115,2773.105,2773.665),
                  (2773.695,2775.325,2771.848,2772.425),
                  (2772.465,2775.155,2769.885,2773.995),
                  (2773.975,2777.665,2770.768,2772.675),
                  (2772.645,2775.998,2771.415,2775.598),
                  (2775.498,2779.955,2773.975,2776.495),
                  (2776.515,2778.935,2776.028,2778.415)]
        bars = [Candle(datetime(2025,1,24)+timedelta(hours=i),*p,0)
                for i,p in enumerate(prices,371)]
        class Boundary:
            def resolve(self,reversal,candle):
                return {373:(2775.745,2778.115),375:(2769.885,2772.675),
                        378:(2777,2779.955)}[reversal.extreme_index]
        engine = ReplayEngine(EngineConfig(),5905,Boundary())
        source = Zone(55,ZoneType.SUPPORT,ZoneState.ACTIVE,2770.365,2772.365,2770.365,371,
                      created_at_index=372)
        source.interactions = [Interaction(110,55,InteractionState.OPEN,2770.365,371)]
        engine.state.zones = [source]
        engine.state.next_zone_id,engine.state.next_interaction_id = 56,111
        engine.current_index = 372
        engine._recent.extend(bars[:2])
        engine._last_datetime = bars[1].datetime
        for bar in bars[2:]:
            engine.process(bar)
        report = engine.state.invalidated_reactions[-1]
        self.assertEqual((report["interaction_id"],report["break_index"]),(113,379))
        self.assertEqual((report["restored_origin_zone_id"],report["restored_interaction_id"]),(57,112))
        zone,move = engine._current(engine.state)
        self.assertEqual((zone.id,move.id),(57,112))
        self.assertTrue(any(r.broken_zone_id==56 and r.break_index==379 for r in move.breaks))


if __name__ == "__main__":
    unittest.main()
