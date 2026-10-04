import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_outgoing_c2_breaks import fixture
from test_engine_results_repository import MemoryClient
from zone_energy.data import EngineResultsRepository
from zone_energy.config import EngineConfig
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType
from zone_energy.replay.replay_engine import ReplayEngine


class FixedBoundary:
    def resolve(self, reversal, candle):
        return 2637.935, 2646.098


class PendingReactionTests(unittest.TestCase):
    def test_real_c11_candidate_never_replaces_support7(self):
        engine = ReplayEngine(EngineConfig(), 5905, FixedBoundary())
        broken = Zone(1, ZoneType.RESISTANCE, ZoneState.ACTIVE,
                      2633.655, 2636.298, 2636.298, 3, created_at_index=4)
        broken.interactions = [Interaction(1, 1, InteractionState.CLOSED, 2636.298, 3,
                                          end_index=7, base_energy=2)]
        origin = Zone(2, ZoneType.SUPPORT, ZoneState.ACTIVE,
                      2630.858, 2632, 2630.998, 7, created_at_index=8)
        origin.interactions = [Interaction(4, 2, InteractionState.OPEN, 2630.998, 7)]
        engine.state.zones = [broken, origin]
        engine.state.next_zone_id = 3
        engine.state.next_interaction_id = 5
        prices = [(2635.704,2637.558,2630.985,2636.348),
                  (2636.365,2639.785,2635.858,2635.915),
                  (2635.915,2646.098,2632.535,2642.488),
                  (2642.518,2644.468,2640.064,2641.665),
                  (2641.704,2646.265,2640.148,2643.165),
                  (2643.155,2647.135,2635.865,2642.764),
                  (2642.754,2650.975,2640.135,2647.485)]
        bars = [Candle(datetime(2025,1,1)+timedelta(hours=i),*p,0)
                for i,p in enumerate(prices,9)]
        engine.current_index = 10
        engine._recent.extend(bars[:2])
        engine._last_datetime = bars[1].datetime
        for candle in bars[2:6]:
            engine.process(candle)
            self.assertEqual(engine._current(engine.state)[1].start_index, 7)
        self.assertEqual(engine.state.pending_reaction["reversal"]["extreme_index"], 11)
        self.assertEqual([(r.broken_zone_id,r.break_index)
                          for r in engine._current(engine.state)[1].breaks], [(1,12)])
        engine.process(bars[6])
        self.assertIsNone(engine.state.pending_reaction)
        self.assertEqual(engine.state.rejected_reactions[-1]["reason"], "close_exited_against_reaction")
        self.assertEqual(engine._current(engine.state)[1].start_index, 7)
        self.assertFalse(any(m.start_index == 11 for z in engine.state.zones for m in z.interactions))

    def test_delayed_role_change_keeps_original_c2_energy_and_is_atomic(self):
        engine, bars, snapshot = fixture()
        engine.process(bars[2])
        c3 = replace(bars[3], low=2661, close=2661.5)
        engine.process(c3)
        self.assertIsNone(engine._current(engine.state))
        self.assertEqual(engine.state.confirmed_c2_breaks, [])
        self.assertIsNotNone(engine.state.pending_reaction)
        departure = Candle(c3.datetime+timedelta(hours=1),2661.5,2665,2661,2663,0)
        before = deepcopy(engine.state)
        def fail(*args):
            raise RuntimeError("checkpoint failure")
        with self.assertRaises(RuntimeError):
            engine.process(departure, before_commit=fail)
        self.assertEqual(engine.state, before)
        engine.process(departure)
        zone, move = engine._current(engine.state)
        self.assertEqual((zone.id,move.start_index),(19,124))
        self.assertEqual(zone.type, ZoneType.SUPPORT)
        record = move.breaks[0]
        energy,median = snapshot.reference_for_break(19)
        self.assertEqual(record.broken_zone_energy_at_break, energy)
        self.assertEqual(record.median_active_zone_energy_at_break, median)
        self.assertEqual(record.break_index,124)
        self.assertEqual(engine.state.confirmed_c2_breaks[0]["confirmation_index"],126)
        self.assertEqual(engine.state.reaction_confirmations[0]["pattern_confirmation_index"],125)
        self.assertEqual(engine.state.reaction_confirmations[0]["departure_index"],126)

    def test_waiting_candidate_checkpoint_preserves_original_pattern_and_snapshot(self):
        engine, bars, _ = fixture()
        engine.process(bars[2])
        engine.process(replace(bars[3], low=2660.5, close=2660.75))
        self.assertIsNotNone(engine.state.pending_reaction)
        repository = EngineResultsRepository(client=MemoryClient())
        identifier = repository.save_checkpoint(engine.state.zones, run_id="pending", symbol="XAUUSD",
            current_candle_index=125, year_candles=5905, config=EngineConfig(),
            replay_context={"pending_reaction":engine.state.pending_reaction})
        saved = repository.get_checkpoint(identifier)["replay_context"]["pending_reaction"]
        self.assertEqual(saved["reversal"]["extreme_index"],124)
        self.assertEqual(saved["c2_breaks"][0]["break_index"],124)
        self.assertEqual(saved["c3"]["close"],2660.75)
        self.assertEqual(saved["reversal"]["type"],"support")

    def test_delayed_reaction_invalidation_restores_previous_origin(self):
        engine, bars, _ = fixture(orphan=False)
        engine.process(bars[2])
        c3 = replace(bars[3], low=2661, close=2661.5)
        engine.process(c3)
        engine.process(Candle(c3.datetime+timedelta(hours=1),2661.5,2665,2661,2663,0))
        engine.process(Candle(c3.datetime+timedelta(hours=2),2659,2660,2657,2658,0))
        self.assertEqual(engine._current(engine.state)[0].id,20)
        self.assertEqual(engine.state.confirmed_c2_breaks,[])
        self.assertFalse(any(move.id == 49 for zone in engine.state.zones for move in zone.interactions))
        self.assertEqual(engine.state.invalidated_reactions[-1]["reaction_index"],124)



if __name__ == "__main__":
    unittest.main()
