from collections import deque
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
import unittest

from zone_energy.config import EngineConfig, EngineTimeframe
from zone_energy.models import Candle, Interaction, InteractionState, PriceSide, Zone, ZoneState, ZoneType
from zone_energy.replay.replay_engine import ReplayEngine
from zero_distance_policy import V2ReplayEngine


class Boundary:
    def resolve(self, reversal, origin):
        return 1360.0, 1361.0


def report_candles():
    return [Candle(datetime(2011, 2, 10, h), *prices, 0.0) for h, prices in (
        (4, (1357.3, 1358.53, 1356.53, 1357.18)),
        (5, (1357.03, 1360.43, 1356.93, 1358.1)),
        (6, (1358.18, 1358.18, 1356.48, 1357.8)))]


def seeded(engine_type=V2ReplayEngine, start_price=1360.43):
    engine = engine_type(EngineConfig(timeframe=EngineTimeframe.H1), 5933, Boundary())
    move = Interaction(id=1800, zone_id=424, state=InteractionState.OPEN,
        start_price=start_price, start_index=6836,
        previous_distance=3.5699999999999363, previous_movement_time=2)
    origin = Zone(id=424, type=ZoneType.SUPPORT, state=ZoneState.ACTIVE,
        lower_price=1356.63, upper_price=1360.95, creation_extreme=1356.63,
        creation_index=6268, created_at_index=6269, interactions=[move])
    target = Zone(id=386, type=ZoneType.SUPPORT, state=ZoneState.BROKEN,
        lower_price=1359.83, upper_price=1361.48, creation_extreme=1359.83,
        creation_index=5586, created_at_index=5587, last_external_price_side=PriceSide.BELOW)
    engine.state.zones = [target, origin]
    engine.state.next_zone_id = 425
    engine.state.next_interaction_id = 1801
    c1, c2, _ = report_candles()
    engine._recent = deque([c1, c2], maxlen=2)
    engine._last_datetime = c2.datetime
    engine.current_index = 6840
    return engine


class ZeroDistancePolicyTests(unittest.TestCase):
    def test_committed_history_revision_is_reported_without_repeating_old_audits(self):
        engine = seeded()
        def revise_history(state, index, candle):
            old = deepcopy(state.rejected_reactions[-1])
            old.update(start_index=6830, end_index=6834, reaction_index=6834,
                       rejected_at=6840, rejected_datetime="2011-02-10T05:00:00")
            state.rejected_reactions.append(old)
        engine.process(report_candles()[2], before_commit=revise_history)
        self.assertEqual(len(engine.recent_policy_rejections), 2)
        self.assertEqual(engine.recent_policy_rejections[-1]["rejected_at"], 6840)
        engine.process(Candle(datetime(2011, 2, 10, 7), 1357.8, 1358.4, 1356.9, 1358.2, 0))
        self.assertEqual(engine.recent_policy_rejections, [])

    def test_failed_commit_does_not_leak_rejections_or_mutate_interaction(self):
        engine = seeded()
        before = deepcopy(engine.state)
        def fail(state, index, candle):
            raise OSError("checkpoint failed")
        with self.assertRaises(OSError):
            engine.process(report_candles()[2], before_commit=fail)
        self.assertEqual(engine.state, before)
        self.assertEqual(getattr(engine, "recent_policy_rejections", []), [])

    def test_report_scenario_rejects_role_change_and_continues(self):
        candle = report_candles()[2]
        original = seeded(ReplayEngine)
        with self.assertRaisesRegex(ValueError, "Interaction distance"):
            original.process(candle)
        engine = seeded()
        events = engine.process(candle)
        self.assertIn("zero_distance_reaction_rejected", events)
        self.assertNotIn("role_change", events)
        self.assertNotIn("reaction_confirmed_by_close", events)
        target, origin = engine.state.zones
        move = origin.interactions[0]
        self.assertEqual((target.type, target.state), (ZoneType.SUPPORT, ZoneState.BROKEN))
        self.assertEqual(move.state, InteractionState.OPEN)
        self.assertIsNone(move.end_price)
        self.assertIsNone(move.base_energy)
        self.assertEqual(engine.state.next_interaction_id, 1801)
        self.assertIsNone(engine.state.pending_reaction)
        self.assertEqual(engine.current_index, 6841)
        rejection = engine.recent_policy_rejections[0]
        self.assertEqual((rejection["interaction_id"], rejection["zone_id"]), (1800, 386))
        self.assertEqual(rejection["reason"], "zero_distance")
        self.assertEqual(rejection["movement_time"], 4)
        self.assertEqual(engine.state.rejected_reactions[-1], rejection)
        engine.process(Candle(datetime(2011, 2, 10, 7), 1357.8, 1358.4, 1356.9, 1358.2, 0))
        self.assertEqual(engine.current_index, 6842)
        self.assertEqual(engine._current(engine.state)[1].id, 1800)
        self.assertEqual(engine.recent_policy_rejections, [])

    def test_nonzero_reaction_matches_unmodified_v1_exactly(self):
        a, b = seeded(ReplayEngine, 1360.42), seeded(V2ReplayEngine, 1360.42)
        self.assertEqual(a.process(report_candles()[2]), b.process(report_candles()[2]))
        self.assertEqual(a.state, b.state)
        self.assertEqual(b.recent_policy_rejections, [])

    def test_waiting_candidate_is_rejected_on_departure(self):
        engine = seeded()
        c1, c2, c3 = report_candles()
        engine.current_index = 6841
        engine._recent = deque([c2, c3], maxlen=2)
        engine._last_datetime = c3.datetime
        engine.state.pending_reaction = dict(zone_id=386, role_change=True,
            reversal=dict(type="resistance", extreme_price=1360.43, extreme_index=6840, detection_index=6841),
            c1=asdict(c1), c2=asdict(c2), c3=asdict(c3), previous_type="support", c2_breaks=[])
        events = engine.process(Candle(datetime(2011, 2, 10, 7), 1357.8, 1358.0, 1356.6, 1357.7, 0))
        self.assertIn("zero_distance_reaction_rejected", events)
        self.assertNotIn("reaction_confirmed_by_close", events)
        self.assertEqual(engine._current(engine.state)[1].id, 1800)
        self.assertEqual(engine.recent_policy_rejections[0]["rejected_at"], 6842)

    def test_new_zone_does_not_start_a_zero_distance_interaction(self):
        engine = seeded()
        engine.state.zones = [engine.state.zones[1]]
        events = engine.process(report_candles()[2])
        self.assertIn("zone_created", events)
        self.assertIn("zero_distance_reaction_rejected", events)
        self.assertEqual(len(engine.state.zones[-1].interactions), 0)
        self.assertEqual(engine._current(engine.state)[1].id, 1800)

    def test_invalid_temporal_order_is_not_suppressed(self):
        engine = seeded()
        c1, c2, c3 = report_candles()
        engine.state.pending_reaction = dict(zone_id=386, role_change=True,
            reversal=dict(type="resistance", extreme_price=1360.43, extreme_index=6836, detection_index=6840),
            c1=asdict(c1), c2=asdict(c2), c3=asdict(c3), previous_type="support", c2_breaks=[])
        before = deepcopy(engine.state)
        with self.assertRaisesRegex(ValueError, "Ending reaction"):
            engine.process(c3)
        self.assertEqual(engine.state, before)
        self.assertEqual(engine.current_index, 6840)


if __name__ == "__main__":
    unittest.main()
