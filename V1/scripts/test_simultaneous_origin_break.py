import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
from zone_energy.config import EngineConfig
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.models import Candle,Interaction,InteractionState,Zone,ZoneState,ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


def fixture(mirrored=False):
    prices = [(2668.295,2669.455,2667.235,2668.895),
              (2668.935,2670.735,2666.985,2669.005),
              (2669.175,2674.255,2667.155,2670.815),
              (2670.755,2671.405,2664.699,2667.125),
              (2667.115,2668.635,2664.479,2666.495),
              (2666.525,2669.645,2664.439,2669.025),
              (2669.025,2671.485,2666.265,2668.165),
              (2668.165,2674.148,2660.815,2662.709),
              (2662.649,2665.835,2659.645,2664.975),
              (2665.015,2672.595,2664.945,2671.478)]
    if mirrored:
        prices = [(-op,-low,-high,-close) for op,high,low,close in prices]
    bars = [Candle(datetime(2025,1,14)+timedelta(hours=i),*p,0) for i,p in enumerate(prices,191)]
    class Boundary:
        def resolve(self,reversal,candle):
            return ((candle.high-1,candle.high) if mirrored else (candle.low,candle.low+1))
    engine = ReplayEngine(EngineConfig(),5905,Boundary())
    def zone(identifier,kind,lower,upper,extreme,index):
        if mirrored:
            kind = ZoneType.SUPPORT if kind == ZoneType.RESISTANCE else ZoneType.RESISTANCE
            lower,upper,extreme = -upper,-lower,-extreme
        return Zone(identifier,kind,ZoneState.ACTIVE,lower,upper,extreme,index,created_at_index=index+1)
    support = zone(23,ZoneType.SUPPORT,2663.795,2666.775,2663.795,124)
    support.interactions = [Interaction(40,23,InteractionState.CLOSED,support.creation_extreme,124,
                                       end_index=130,base_energy=5)]
    resistance = zone(32,ZoneType.RESISTANCE,2671.519,2675.155,2675.155,190)
    resistance.interactions = [Interaction(61,32,InteractionState.OPEN,resistance.creation_extreme,190)]
    engine.state.zones = [support,resistance]
    engine.state.next_zone_id,engine.state.next_interaction_id = 33,62
    engine.current_index = 192
    engine._recent.extend(bars[:2])
    engine._last_datetime = bars[1].datetime
    for bar in bars[2:7]:
        engine.process(bar)
    return engine,bars


class SimultaneousBreakTests(unittest.TestCase):
    def test_real_198_break_waits_for_199_and_new_199_low_is_confirmed_at_200(self):
        for mirrored in (False,True):
            engine,bars = fixture(mirrored)
            previous = engine._current(engine.state)[1]
            self.assertEqual(previous.start_index,196)
            snapshot = MarketEnergySnapshotCalculator(EngineConfig()).capture(engine.state.zones,198,5905)
            engine.process(bars[7])
            self.assertEqual(engine._current(engine.state)[1].start_index,196)
            self.assertEqual(engine.state.invalidated_reactions,[])
            self.assertEqual(engine.state.pending_origin_break["break_index"],198)
            self.assertEqual(next(z for z in engine.state.zones if z.id==23).state,ZoneState.BROKEN)
            before = deepcopy(engine.state)
            def fail(*args):
                raise RuntimeError("checkpoint failure")
            with self.assertRaises(RuntimeError):
                engine.process(bars[8],before_commit=fail)
            self.assertEqual(engine.state,before)
            engine.process(bars[8])
            zone,move = engine._current(engine.state)
            self.assertEqual((zone.id,move.start_index),(32,198))
            record = next(r for r in move.breaks if r.broken_zone_id==23)
            self.assertEqual(record.break_index,198)
            energy,median = snapshot.reference_for_break(23)
            self.assertEqual(record.broken_zone_energy_at_break,energy)
            self.assertEqual(record.median_active_zone_energy_at_break,median)
            self.assertEqual(engine.state.invalidated_reactions,[])
            self.assertIsNone(engine.state.pending_origin_break)
            engine.process(bars[9])
            self.assertEqual(engine._current(engine.state)[1].start_index,199)
            self.assertEqual(sum(r.broken_zone_id==23 and r.break_index==198
                for z in engine.state.zones for m in z.interactions for r in m.breaks),1)

    def test_failed_opposite_pattern_invalidates_at_original_break_index(self):
        engine,bars = fixture()
        engine.process(bars[7])
        engine.process(replace(bars[8],high=2676))
        self.assertEqual(engine.state.invalidated_reactions[-1]["reaction_index"],196)
        self.assertEqual(engine.state.invalidated_reactions[-1]["break_index"],198)
        self.assertIsNone(engine.state.pending_origin_break)
        self.assertEqual(engine._current(engine.state)[1].start_index,193)


if __name__ == "__main__":
    unittest.main()
