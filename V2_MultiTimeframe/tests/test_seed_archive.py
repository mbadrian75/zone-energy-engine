from copy import copy, deepcopy
from datetime import timedelta
import gc
from pathlib import Path
from types import SimpleNamespace
import tracemalloc
import unittest

from seed_archive import SeedArchive, SeedReference
from zero_distance_policy import V2ReplayEngine
from zone_energy.replay.replay_engine import ReplayEngine
from zone_energy.config import EngineConfig
from zone_energy.models import InteractionState, Candle
from test_v1_adapter import Boundary, v1_candles


class SyntheticTransitions:
    def _process_once(self, candle):
        self.state = deepcopy(self.state)
        self.current_index += 1
        self.state.zones = [SimpleNamespace(interactions=[SimpleNamespace(
            id=self.current_index, state=InteractionState.OPEN)])]
        self.state.unattributed_breaks = [{"payload": bytearray(32768)}]
        return []


class ArchivedTransitions(SyntheticTransitions, V2ReplayEngine):
    pass


class ResidentTransitions(SyntheticTransitions, ReplayEngine):
    pass


class SeedArchiveTests(unittest.TestCase):
    def test_real_invalidation_matches_v1_every_candle(self):
        a = ReplayEngine(EngineConfig(), 1000, Boundary())
        b = V2ReplayEngine(EngineConfig(), 1000, Boundary())
        rows = v1_candles()[:3]
        rows[2] = Candle(rows[2].datetime, 102, 109, 102, 109, 0)
        rows.append(Candle(rows[-1].datetime + timedelta(hours=1), 98, 99, 90, 95, 0))
        try:
            for row in rows:
                self.assertEqual(a.process(row), b.process(row))
                self.assertEqual(a.state, b.state)
                self.assertEqual(a.current_index, b.current_index)
            self.assertGreater(len(b.state.invalidated_reactions), 0)
            self.assertGreater(b._seed_archive.loads, 0)
        finally:
            b.close()

    def test_no_live_engine_chain_and_all_prior_seeds_recoverable(self):
        e = ArchivedTransitions(EngineConfig(), 1000, Boundary())
        try:
            row = v1_candles()[0]
            for _ in range(200):
                e.process(row)
                self.assertIsInstance(e._reaction_seed, SeedReference)
            seed, count = e._reaction_seed, 0
            while seed is not None:
                recovered = copy(seed)
                self.assertIs(recovered.boundary_service, e.boundary_service)
                self.assertIs(recovered._seed_archive, e._seed_archive)
                self.assertEqual(recovered.current_index, 198 - count)
                seed = recovered._reaction_seed
                count += 1
            self.assertEqual(count, 200)
        finally:
            directory = Path(e._seed_archive.directory.name)
            e.close()
            self.assertFalse(directory.exists())

    def test_retained_memory_is_reduced_on_1000_transitions(self):
        def measure(cls):
            gc.collect()
            tracemalloc.start()
            engine = cls(EngineConfig(), 1000, Boundary())
            try:
                for _ in range(1000):
                    engine.process(v1_candles()[0])
                retained, peak = tracemalloc.get_traced_memory()
                disk = getattr(getattr(engine, "_seed_archive", None), "bytes", 0)
                return retained, peak, disk
            finally:
                tracemalloc.stop()
                if isinstance(engine, V2ReplayEngine):
                    engine.close()
        baseline = measure(ResidentTransitions)
        archived = measure(ArchivedTransitions)
        self.assertLess(archived[0], baseline[0] // 4)
        print("Seed memory regression (retained, peak, disk bytes):", baseline, archived)

    def test_failed_commit_does_not_advance_seed(self):
        engine = V2ReplayEngine(EngineConfig(), 1000, Boundary())
        try:
            rows = v1_candles()
            for row in rows[:3]:
                engine.process(row)
            prior, state = engine._reaction_seed, deepcopy(engine.state)
            def fail(*args):
                raise OSError("checkpoint failed")
            with self.assertRaises(OSError):
                engine.process(rows[3], before_commit=fail)
            self.assertIs(engine._reaction_seed, prior)
            self.assertEqual(engine.state, state)
        finally:
            engine.close()

    def test_io_error_and_corrupt_seed_propagate(self):
        archive = SeedArchive(object())
        try:
            ref = archive.store(SimpleNamespace(value=42))
            self.assertEqual(copy(ref).value, 42)
            path = Path(archive.directory.name) / ref.name
            path.write_bytes(b"corrupt")
            with self.assertRaises(OSError):
                copy(ref)
        finally:
            archive.close()
