import sys
import math
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_engine_results_repository import MemoryClient
from test_replay_engine import Boundary
from zone_energy.config import EngineConfig
from zone_energy.data import EngineResultsRepository
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.models import Candle,Interaction,InteractionState,Zone,ZoneState,ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


def fixture(mirrored=False, extra=False, undefined=False, orphan=True):
    prices = [(2658.285,2666.775,2658.248,2666.575),
              (2666.595,2666.645,2662.074,2662.218),
              (2662.164,2666.714,2660.268,2664.124),
              (2664.234,2666.444,2662.068,2664.744)]
    if orphan:
        # Exercise retained C2 credits when there really is no OPEN origin.
        prices[2] = (2662.164,2666.5,2660.268,2664.124)
    if mirrored:
        prices = [(-op,-low,-high,-close) for op,high,low,close in prices]
    bars = [Candle(datetime(2025,1,9,hour),*values,0)
            for hour,values in zip((1,2,3,4),prices)]
    kind = ZoneType.SUPPORT if mirrored else ZoneType.RESISTANCE
    price = lambda value: -value if mirrored else value
    def zone(zone_id,lower,upper,extreme,index):
        bounds = sorted((price(lower),price(upper)))
        return Zone(zone_id,kind,ZoneState.ACTIVE,*bounds,price(extreme),index,
                    created_at_index=index+1)
    target = zone(19,2660,2662,2661.945,119)
    target.interactions = [Interaction(47,19,InteractionState.CLOSED,price(2661.945),119,
                                      end_index=121,base_energy=None if undefined else 5)]
    source = zone(20,2666,2666.775,2666.775,122)
    source.interactions = [Interaction(48,20,InteractionState.OPEN,price(2666.775),122)]
    if orphan:
        source.interactions = []
    engine = ReplayEngine(EngineConfig(),5905,Boundary())
    engine.state.zones = [target,source]
    if extra:
        other = zone(18,2659,2661,2660,118)
        other.interactions = [Interaction(46,18,InteractionState.CLOSED,price(2660),118,
                                         end_index=120,base_energy=3)]
        engine.state.zones.insert(0,other)
    engine.state.next_zone_id = 21
    engine.state.next_interaction_id = 49
    engine.current_index = 123
    engine._recent.extend(bars[:2])
    engine._last_datetime = bars[1].datetime
    snapshot = MarketEnergySnapshotCalculator(EngineConfig()).capture(engine.state.zones,124,5905)
    return engine,bars,snapshot


class OutgoingC2Tests(unittest.TestCase):
    def test_old_role_same_zone_c2_snapshot_and_no_evidence_before_c3(self):
        for mirrored in (False,True):
            engine,bars,snapshot = fixture(mirrored)
            old_history = deepcopy(engine.state.zones[0].interactions)
            engine.process(bars[2])
            self.assertEqual(len(engine.state.pending_c2_breaks),1)
            self.assertEqual(len(engine.state.unattributed_breaks),1)
            self.assertEqual(engine.state.confirmed_c2_breaks,[])
            self.assertIsNone(engine._current(engine.state))
            before = deepcopy(engine.state)
            def fail(*args):
                raise RuntimeError("checkpoint failure")
            with self.assertRaises(RuntimeError):
                engine.process(bars[3],before_commit=fail)
            self.assertEqual(engine.state,before)
            events = engine.process(bars[3])
            self.assertIn("c2_break_confirmed",events)
            origin,move = engine._current(engine.state)
            self.assertEqual((origin.id,move.id),(19,49))
            self.assertEqual(origin.interactions[:-1],old_history)
            record = move.breaks[0]
            self.assertEqual((record.broken_zone_id,record.break_index,record.break_time_from_origin),(19,124,0))
            energy,median = snapshot.reference_for_break(19)
            self.assertEqual(record.broken_zone_energy_at_break,energy)
            self.assertEqual(record.median_active_zone_energy_at_break,median)
            self.assertAlmostEqual(record.displacement,2.124)
            # Orphan fixture has no retained incoming valid reaction.
            self.assertIsNone(move.previous_movement_time)
            self.assertIsNone(record.persistence)
            self.assertIsNone(record.break_evidence)
            self.assertEqual(engine.state.unattributed_breaks,[])
            self.assertEqual(engine.state.pending_c2_breaks,[])
            report = engine.state.confirmed_c2_breaks[0]
            self.assertTrue(report["same_zone_role_change"])
            self.assertNotEqual(report["broken_zone_type"],report["origin_zone_type"])

    def test_multiple_c2_breaks_share_frozen_median_and_are_counted_once(self):
        engine,bars,snapshot = fixture(extra=True)
        engine.process(bars[2])
        engine.process(bars[3])
        records = engine._current(engine.state)[1].breaks
        self.assertEqual({record.broken_zone_id for record in records},{18,19})
        self.assertEqual(len(records),2)
        self.assertTrue(all(record.median_active_zone_energy_at_break==snapshot.median_active_energy
                            for record in records))
        with self.assertRaises(ValueError):
            engine.process(bars[3])
        self.assertEqual(len(engine._current(engine.state)[1].breaks),2)

    def test_missing_c3_pattern_expires_candidate_without_reassignment(self):
        engine,bars,_ = fixture()
        engine.process(bars[2])
        engine.process(Candle(bars[3].datetime,2665,2667,2659,2666.5,0))
        self.assertEqual(engine.state.pending_c2_breaks,[])
        self.assertEqual(engine.state.confirmed_c2_breaks,[])
        self.assertEqual(len(engine.state.unattributed_breaks),1)

    def test_undefined_old_energy_stays_undefined(self):
        engine,bars,_ = fixture(undefined=True)
        engine.process(bars[2])
        engine.process(bars[3])
        record = engine._current(engine.state)[1].breaks[0]
        self.assertIsNone(record.broken_zone_energy_at_break)
        self.assertIsNone(record.break_evidence)

    def test_invalidation_discards_credit_and_checkpoints_are_immutable(self):
        engine,bars,_ = fixture(orphan=False)
        engine.process(bars[2])
        repository = EngineResultsRepository(client=MemoryClient())
        def save(index):
            return repository.save_checkpoint(engine.state.zones,run_id="c2",symbol="XAUUSD",
                current_candle_index=index,year_candles=5905,config=EngineConfig(),
                replay_context={"pending_c2_breaks":engine.state.pending_c2_breaks,
                                "confirmed_c2_breaks":engine.state.confirmed_c2_breaks})
        first = save(124)
        saved = repository.get_checkpoint(first)
        engine.process(bars[3])
        confirmed = save(125)
        self.assertEqual(repository.load_zones(confirmed),engine.state.zones)
        self.assertEqual(repository.get_checkpoint(first),saved)
        engine.process(Candle(bars[3].datetime+timedelta(hours=1),2659,2659.5,2656,2657,0))
        self.assertEqual(engine.state.confirmed_c2_breaks,[])
        self.assertFalse(any(event["candle_index"]==124 for event in engine.state.unattributed_breaks))
        self.assertEqual(engine._current(engine.state)[1].breaks[0].break_index,124)
        self.assertEqual(len(engine.state.invalidated_reactions),1)
        self.assertEqual(engine._current(engine.state)[1].id,48)


if __name__ == "__main__":
    unittest.main()
