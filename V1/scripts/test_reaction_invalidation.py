import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_role_change_with_reference import scenario
from test_replay_engine import Boundary
from zone_energy.config import EngineConfig
from zone_energy.engine.effective_zone_energy_calculator import EffectiveZoneEnergyCalculator
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


class InvalidationTests(unittest.TestCase):
    def test_real_candle_82_restores_support_at_77(self):
        prices = [
            (2634.548,2635.048,2632.775,2634.895),
            (2634.875,2641.105,2634.704,2638.855),
            (2638.845,2640.045,2636.725,2638.498),
            (2638.498,2640.125,2637.355,2639.378),
            (2639.378,2639.695,2637.144,2638.055),
            (2638.055,2645.655,2636.855,2644.405),
            (2644.405,2646.515,2639.648,2640.155),
            (2640.148,2641.998,2637.945,2640.348),
            (2640.348,2644.625,2639.885,2642.485),
            (2642.425,2644.025,2640.025,2641.175),
            (2641.155,2644.565,2641.148,2643.725),
            (2643.715,2648.478,2641.885,2648.255),
            (2648.198,2652.575,2647.234,2651.395)]
        class LocalBoundaries:
            def resolve(self, reversal, candle):
                # Real origin/support boundaries; other zones are test fixtures.
                return {1:(2638,2641.105),5:(2636.855,2639.355),
                        6:(2646.025,2646.515),8:(2644.448,2647.275)}[reversal.extreme_index]
        engine = ReplayEngine(EngineConfig(),5905,LocalBoundaries())
        for index,values in enumerate(prices):
            engine.process(Candle(datetime(2025,1,6)+timedelta(hours=index),*values,0))
        origin,move = engine._current(engine.state)
        self.assertEqual((move.start_index,move.start_price),(7,2637.945))
        invalid = engine.state.invalidated_reactions[-1]
        self.assertEqual((invalid["reaction_index"],invalid["break_index"]),(8,12))
        broken = next(zone for zone in engine.state.zones if zone.id==invalid["zone_id"])
        self.assertEqual(broken.state,ZoneState.BROKEN)
        self.assertEqual(broken.interactions,[])
        self.assertTrue(any(record.broken_zone_id==broken.id and record.break_index==12 for record in move.breaks))

    def test_restore_origin_replay_intervening_breaks_preserve_energy_and_atomicity(self):
        target, source, reversal, bars = scenario(ZoneType.SUPPORT)
        bars[1] = replace(bars[1], low=98)
        old_history = deepcopy(target.interactions)
        source.interactions.append(Interaction(2, source.id, InteractionState.OPEN,90,15))
        other = Zone(3,ZoneType.RESISTANCE,ZoneState.ACTIVE,92,96,96,8,created_at_index=9)
        other.interactions = [Interaction(4,3,InteractionState.CLOSED,96,8,end_index=12,base_energy=3)]
        engine = ReplayEngine(EngineConfig(),1000,Boundary())
        engine.state.zones = [target,source,other]
        engine.state.next_zone_id = 4
        engine.state.next_interaction_id = 5
        engine.current_index = 20
        engine._recent.extend(bars[:2])
        engine._last_datetime = bars[1].datetime
        engine.process(bars[2])
        engine.process(Candle(bars[2].datetime+timedelta(hours=1),100,102,100,101,0))
        self.assertEqual(engine.state.unattributed_breaks,[])
        self.assertEqual(engine._current(engine.state)[1].breaks[0].broken_zone_id,3)
        before = deepcopy(engine.state)
        from test_engine_results_repository import MemoryClient
        from zone_energy.data import EngineResultsRepository
        repository = EngineResultsRepository(client=MemoryClient())
        old_checkpoint = repository.save_checkpoint(
            engine.state.zones,run_id="invalidation",symbol="XAUUSD",current_candle_index=22,
            year_candles=1000,config=EngineConfig())
        old_document = repository.get_checkpoint(old_checkpoint)
        recent = tuple(engine._recent)
        window = engine._reaction_window
        breaking = Candle(bars[2].datetime+timedelta(hours=2),112,116,111,115,0)
        def fail(*args):
            raise RuntimeError("checkpoint failure")
        with self.assertRaises(RuntimeError):
            engine.process(breaking,before_commit=fail)
        self.assertEqual(engine.state,before)
        self.assertEqual(tuple(engine._recent),recent)
        self.assertEqual(engine._reaction_window,window)
        self.assertEqual(engine.current_index,22)
        events = engine.process(breaking)
        self.assertIn("reaction_invalidated",events)
        target, source, other = engine.state.zones
        self.assertEqual(target.state,ZoneState.BROKEN)
        self.assertEqual(target.type,ZoneType.RESISTANCE)
        self.assertEqual(target.interactions,old_history)
        self.assertEqual(source.interactions[-1].state,InteractionState.OPEN)
        self.assertEqual(source.interactions[-1].start_index,15)
        records = source.interactions[-1].breaks
        self.assertEqual([(r.broken_zone_id,r.break_index) for r in records],[(3,21),(1,23)])
        expected = EffectiveZoneEnergyCalculator(EngineConfig()).calculate(target,23,1000)
        self.assertAlmostEqual(records[-1].broken_zone_energy_at_break,expected)
        self.assertEqual(engine.state.unattributed_breaks,[])
        audit = engine.state.invalidated_reactions[0]
        self.assertEqual((audit["interaction_id"],audit["restored_interaction_id"]),(5,2))
        self.assertEqual(audit["invalid_interaction"]["start_index"],20)
        self.assertEqual(len([m for z in engine.state.zones for m in z.interactions
                              if m.state==InteractionState.OPEN]),1)
        new_checkpoint = repository.save_checkpoint(
            engine.state.zones,run_id="invalidation",symbol="XAUUSD",current_candle_index=23,
            year_candles=1000,config=EngineConfig(),
            replay_context={"invalidated_reactions":engine.state.invalidated_reactions})
        self.assertEqual(repository.get_checkpoint(old_checkpoint),old_document)
        self.assertEqual(repository.load_zones(new_checkpoint),engine.state.zones)
        self.assertEqual(repository.get_checkpoint(new_checkpoint)["replay_context"]["invalidated_reactions"],
                         engine.state.invalidated_reactions)


if __name__ == "__main__":
    unittest.main()
