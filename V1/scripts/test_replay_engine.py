import sys
import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from test_engine_results_repository import MemoryClient
from zone_energy.config import EngineConfig
from zone_energy.data import EngineResultsRepository
from zone_energy.models import Candle, Interaction, InteractionState
from zone_energy.replay.replay_engine import ReplayEngine
from zone_energy.replay.replay_runner import ReplayRunner


def candles():
    start = datetime(2025, 1, 1)
    prices = [(110, 112, 105, 108), (108, 110, 100, 102),
              (102, 111, 102, 109), (109, 130, 108, 125),
              (125, 128, 110, 115), (115, 120, 95, 100),
              (100, 122, 98, 118), (94, 96, 89, 90)]
    return [Candle(start + timedelta(hours=index), *values, 0)
            for index, values in enumerate(prices)]


class Boundary:
    def resolve(self, reversal, origin):
        return origin.low, origin.high


class Market:
    def __init__(self, items):
        self.items = items

    def stream_candles(self, timeframe, start, end):
        return iter(self.items)


class ReplayEngineTests(unittest.TestCase):
    def engine(self):
        return ReplayEngine(EngineConfig(), 1000, Boundary())

    def test_c3_confirmation_and_single_open_move_at_every_step(self):
        engine = self.engine()
        items = candles()
        engine.process(items[0])
        engine.process(items[1])
        self.assertEqual(engine.state.zones, [])
        for item in items[2:7]:
            engine.process(item)
            opened = [move for zone in engine.state.zones for move in zone.interactions
                      if move.state == InteractionState.OPEN]
            self.assertEqual(len(opened), 1)
        self.assertEqual(len(engine.state.zones), 3)
        support, resistance, new_support = engine.state.zones
        self.assertEqual(resistance.interactions[0].end_index, 5)
        self.assertEqual(resistance.interactions[0].end_price, 95)
        self.assertAlmostEqual(resistance.interactions[0].base_energy, 35 / 30)
        # The new low (95) is outside the original support [100, 110].
        self.assertEqual(len(support.interactions), 1)
        self.assertEqual(new_support.interactions[-1].start_index, 5)

    def test_break_belongs_to_single_current_reaction(self):
        engine = self.engine()
        for candle in candles():
            engine.process(candle)
        opened = [(zone, move) for zone in engine.state.zones for move in zone.interactions
                  if move.state == InteractionState.OPEN]
        self.assertEqual(len(opened), 1)
        zone, move = opened[0]
        self.assertEqual({record.broken_zone_id for record in move.breaks}, {1, 3})
        self.assertTrue(all(record.break_index == 7 for record in move.breaks))
        self.assertEqual(zone.id, 2)

    def test_checkpoint_failure_leaves_candle_uncommitted(self):
        engine = self.engine()
        items = candles()
        for candle in items[:2]:
            engine.process(candle)
        before = deepcopy(engine.state)
        def fail(*args):
            raise RuntimeError("Database write failed")
        with self.assertRaises(RuntimeError):
            engine.process(items[2], before_commit=fail)
        self.assertEqual(engine.state, before)
        self.assertEqual(engine.current_index, 1)
        engine.process(items[2])
        self.assertEqual(len(engine.state.zones), 1)

    def test_duplicate_timestamp_and_multiple_open_history_are_rejected(self):
        engine = self.engine()
        items = candles()
        for candle in items[:3]:
            engine.process(candle)
        with self.assertRaises(ValueError):
            engine.process(items[2])
        zone = engine.state.zones[0]
        zone.interactions.append(Interaction(99, zone.id, InteractionState.OPEN, 101, 2))
        with self.assertRaises(ValueError):
            engine.process(items[3])

    def test_runner_saves_periodic_and_final_recoverable_checkpoints(self):
        client = MemoryClient()
        results = EngineResultsRepository(client=client)
        runner = ReplayRunner(Market(candles()[:7]), results, Boundary(), EngineConfig(), 1000)
        summary = runner.run(start=datetime(2025, 1, 1), end=datetime(2025, 2, 1),
                             run_id="sample", checkpoint_every=3)
        self.assertEqual(summary["candles"], 7)
        self.assertEqual(len(client.collection.documents), 3)
        restored = results.load_zones(summary["last_checkpoint"])
        self.assertEqual(restored, runner.engine.state.zones)
        context = results.get_checkpoint(summary["last_checkpoint"])["replay_context"]
        self.assertEqual(context["candle_datetime"], candles()[6].datetime)

    def test_empty_replay_does_not_write_checkpoint(self):
        client = MemoryClient()
        runner = ReplayRunner(Market([]), EngineResultsRepository(client=client),
                              Boundary(), EngineConfig(), 1000)
        with self.assertRaises(ValueError):
            runner.run(start=datetime(2025, 1, 1), end=datetime(2025, 2, 1), run_id="empty")
        self.assertEqual(client.collection.documents, {})

    def test_latest_active_return_wins_regardless_of_zone_order(self):
        from test_role_change_with_reference import scenario
        from zone_energy.models import ZoneState, ZoneType
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            for newest_first in (False, True):
                with self.subTest(kind=kind, newest_first=newest_first):
                    old, source, reversal, pattern = scenario(kind)
                    old.type = reversal.type
                    old.state = ZoneState.ACTIVE
                    old.interactions = []
                    old.last_interaction_origin_index = None
                    newest = deepcopy(old)
                    newest.id = 3
                    newest.creation_index = 17
                    newest.created_at_index = 18
                    source.interactions.append(Interaction(
                        2, source.id, InteractionState.OPEN,
                        source.creation_extreme, source.creation_index))
                    engine = self.engine()
                    engine.state.zones = ([newest, old, source] if newest_first
                                          else [old, source, newest])
                    engine.state.next_zone_id = 4
                    engine.state.next_interaction_id = 3
                    engine.current_index = 20
                    engine._recent.extend(pattern[:2])
                    engine._last_datetime = pattern[1].datetime
                    events = engine.process(pattern[2])
                    self.assertIn("return_reaction", events)
                    opened = [move for zone in engine.state.zones for move in zone.interactions
                              if move.state == InteractionState.OPEN]
                    self.assertEqual(len(opened), 1)
                    self.assertEqual(opened[0].zone_id, newest.id)
                    unchanged = next(zone for zone in engine.state.zones if zone.id == old.id)
                    self.assertEqual(unchanged.interactions, [])

    def test_ambiguous_reaction_rolls_back_current_candle(self):
        engine = self.engine()
        for candle in candles()[:7]:
            engine.process(candle)
        duplicate = deepcopy(engine.state.zones[1])
        duplicate.id = 99
        for move in duplicate.interactions:
            move.id += 100
            move.zone_id = 99
        engine.state.zones.append(duplicate)
        before = deepcopy(engine.state)
        with self.assertRaisesRegex(ValueError, "overlaps multiple"):
            engine.process(candles()[7])
        self.assertEqual(engine.state, before)
        self.assertEqual(engine.current_index, 6)

    def test_physical_break_without_confirmed_direction_is_observed(self):
        engine = self.engine()
        items = candles()[:3]
        items[2] = Candle(items[2].datetime, 102, 109, 102, 109, 0)
        for item in items:
            engine.process(item)
        engine.process(Candle(items[-1].datetime + timedelta(hours=1), 98, 99, 90, 95, 0))
        self.assertEqual(engine.state.zones[0].state.value, "broken")
        self.assertEqual(len(engine.state.unattributed_breaks), 1)
        self.assertEqual(engine.state.zones[0].interactions, [])
        self.assertEqual(len(engine.state.invalidated_reactions), 1)
        self.assertIsNone(engine.state.invalidated_reactions[0]["restored_origin_zone_id"])

    def test_active_return_precedes_role_change_regardless_of_zone_order(self):
        from test_role_change_with_reference import scenario
        from zone_energy.models import ZoneState, ZoneType
        for original_type in (ZoneType.RESISTANCE, ZoneType.SUPPORT):
            for active_first in (False, True):
                with self.subTest(original_type=original_type, active_first=active_first):
                    target, source, reversal, pattern = scenario(original_type)
                    active = deepcopy(target)
                    active.id = 3
                    active.type = reversal.type
                    active.state = ZoneState.ACTIVE
                    active.interactions = []
                    active.last_interaction_origin_index = None
                    source.interactions.append(Interaction(
                        2, source.id, InteractionState.OPEN,
                        source.creation_extreme, source.creation_index))
                    engine = self.engine()
                    engine.state.zones = ([active, target, source] if active_first
                                          else [target, source, active])
                    engine.state.next_zone_id = 4
                    engine.state.next_interaction_id = 3
                    engine.current_index = 20
                    engine._recent.extend(pattern[:2])
                    engine._last_datetime = pattern[1].datetime
                    events = engine.process(pattern[2])
                    self.assertIn("return_reaction", events)
                    self.assertNotIn("role_change", events)
                    broken = next(zone for zone in engine.state.zones if zone.id == target.id)
                    self.assertEqual(broken.state, ZoneState.BROKEN)
                    self.assertEqual(broken.type, original_type)
                    opened = [move for zone in engine.state.zones for move in zone.interactions
                              if move.state == InteractionState.OPEN]
                    self.assertEqual(len(opened), 1)
                    self.assertEqual(opened[0].zone_id, active.id)

    def test_newest_broken_zone_wins_role_change_and_ties_roll_back(self):
        from test_role_change_with_reference import scenario
        from zone_energy.models import ZoneState, ZoneType
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            for newest_first in (False, True):
                for tied in (False, True):
                    with self.subTest(kind=kind, newest_first=newest_first, tied=tied):
                        old, source, reversal, pattern = scenario(kind)
                        newest = deepcopy(old)
                        newest.id = 3
                        newest.creation_index = old.creation_index if tied else 17
                        newest.created_at_index = newest.creation_index + 1
                        newest.interactions = []
                        newest.last_interaction_origin_index = None
                        source.interactions.append(Interaction(
                            2, source.id, InteractionState.OPEN,
                            source.creation_extreme, source.creation_index))
                        engine = self.engine()
                        engine.state.zones = ([newest, old, source] if newest_first
                                              else [old, source, newest])
                        engine.state.next_zone_id = 4
                        engine.state.next_interaction_id = 3
                        engine.current_index = 20
                        engine._recent.extend(pattern[:2])
                        engine._last_datetime = pattern[1].datetime
                        before = deepcopy(engine.state)
                        if tied:
                            with self.assertRaisesRegex(ValueError, "overlaps multiple"):
                                engine.process(pattern[2])
                            self.assertEqual(engine.state, before)
                            self.assertEqual(engine.current_index, 20)
                        else:
                            events = engine.process(pattern[2])
                            self.assertIn("role_change", events)
                            opened = [move for zone in engine.state.zones for move in zone.interactions
                                      if move.state == InteractionState.OPEN]
                            self.assertEqual(len(opened), 1)
                            self.assertEqual(opened[0].zone_id, newest.id)
                            unchanged = next(zone for zone in engine.state.zones if zone.id == old.id)
                            self.assertEqual(unchanged.state, ZoneState.BROKEN)
                            self.assertEqual(unchanged.type, kind)
                            self.assertEqual(unchanged.interactions, old.interactions)

    def test_role_change_closes_old_move_and_starts_one_new_move(self):
        from test_role_change_with_reference import scenario
        from zone_energy.models import ZoneType
        target, source, _, pattern = scenario(ZoneType.RESISTANCE)
        source.interactions.append(Interaction(2, source.id, InteractionState.OPEN, 130, 15))
        engine = self.engine()
        engine.state.zones = [target, source]
        engine.state.next_zone_id = 3
        engine.state.next_interaction_id = 3
        engine.current_index = 20
        engine._recent.extend(pattern[:2])
        engine._last_datetime = pattern[1].datetime
        events = engine.process(pattern[2])
        self.assertIn("role_change", events)
        opened = [move for zone in engine.state.zones for move in zone.interactions
                  if move.state == InteractionState.OPEN]
        self.assertEqual(len(opened), 1)
        self.assertEqual(opened[0].zone_id, target.id)
        self.assertEqual(opened[0].previous_distance, 28)
        self.assertEqual(engine.state.zones[1].interactions[0].state, InteractionState.CLOSED)


if __name__ == "__main__":
    unittest.main()
