import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_role_change_with_reference import scenario
from test_replay_engine import Boundary
from zone_energy.config import EngineConfig
from zone_energy.engine.reversal_detector import ReversalDetector
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


class ContextualReversalTests(unittest.TestCase):
    def test_real_candle_124_selects_support_after_resistance(self):
        prices = [(2658.285,2666.775,2658.248,2666.575),
                  (2666.595,2666.645,2662.074,2662.218),
                  (2662.164,2666.714,2660.268,2664.124),
                  (2664.234,2666.444,2662.068,2664.744)]
        bars = [Candle(datetime(2025,1,9,hour), *values, 0)
                for hour, values in zip((1,2,3,4), prices)]
        engine = ReplayEngine(EngineConfig(), 5905, Boundary())
        origin = Zone(19, ZoneType.RESISTANCE, ZoneState.ACTIVE,
                      2663.795,2666.775,2666.775,122,created_at_index=123)
        origin.interactions = [Interaction(45,19,InteractionState.OPEN,2666.775,122)]
        engine.state.zones = [origin]
        engine.state.next_zone_id = 20
        engine.state.next_interaction_id = 46
        engine.current_index = 123
        engine._recent.extend(bars[:2])
        engine._last_datetime = bars[1].datetime
        engine.process(bars[2])
        self.assertEqual(len(engine.state.zones), 1)  # Wait for C3.
        engine.process(bars[3])
        old, new = engine.state.zones
        self.assertEqual(old.interactions[0].state, InteractionState.CLOSED)
        self.assertEqual((old.interactions[0].end_index,old.interactions[0].end_price), (124,2660.268))
        self.assertEqual(new.type, ZoneType.SUPPORT)
        self.assertEqual(new.interactions[0].start_index, 124)

    def test_dual_extreme_uses_opposite_role_and_confirmation_accepts_it(self):
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            target, source, reversal, bars = scenario(kind)
            bars[1] = (replace(bars[1], low=98) if kind == ZoneType.SUPPORT
                       else replace(bars[1], high=112))
            # The reaction extreme is unchanged; the other extreme now also qualifies.
            self.assertIsNone(ReversalDetector.detect(*bars,19,20,21))
            detected = ReversalDetector.detect(*bars,19,20,21,previous_type=kind)
            self.assertEqual(detected, reversal)
            source.interactions.append(Interaction(2,source.id,InteractionState.OPEN,
                                                   source.creation_extreme,15))
            engine = ReplayEngine(EngineConfig(),1000,Boundary())
            engine.state.zones = [target,source]
            engine.state.next_zone_id = 3
            engine.state.next_interaction_id = 3
            engine.current_index = 20
            engine._recent.extend(bars[:2])
            engine._last_datetime = bars[1].datetime
            before = deepcopy(engine.state)
            def fail(*args):
                raise RuntimeError("checkpoint failure")
            with self.assertRaises(RuntimeError):
                engine.process(bars[2],before_commit=fail)
            self.assertEqual(engine.state,before)
            self.assertIn("role_change",engine.process(bars[2]))
            self.assertEqual(engine.state.zones[0].type,reversal.type)


if __name__ == "__main__":
    unittest.main()
