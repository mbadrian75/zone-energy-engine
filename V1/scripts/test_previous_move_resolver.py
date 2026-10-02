import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from zone_energy.engine.interaction_closer import InteractionCloser
from zone_energy.engine.previous_move_resolver import PreviousMoveResolver
from zone_energy.models import Interaction, InteractionState, Zone, ZoneState, ZoneType


def zone(zone_id, kind, price, index):
    return Zone(
        id=zone_id, type=kind, state=ZoneState.ACTIVE,
        lower_price=price - 1, upper_price=price + 1,
        creation_extreme=price, creation_index=index,
    )


def movement(zone_id, interaction_id, price, index):
    return Interaction(
        id=interaction_id, zone_id=zone_id, state=InteractionState.OPEN,
        start_price=price, start_index=index,
    )


class PreviousMoveResolverTests(unittest.TestCase):
    def setup_move(self, kind=ZoneType.SUPPORT):
        other_kind = ZoneType.RESISTANCE if kind == ZoneType.SUPPORT else ZoneType.SUPPORT
        source = zone(1, other_kind, 130, 10)
        origin = zone(2, kind, 100, 20)
        incoming = movement(source.id, 10, 130, 10)
        InteractionCloser.close(incoming, source, origin)
        source.interactions.append(incoming)
        current = movement(origin.id, 11, 100, 20)
        return source, origin, incoming, current

    def test_both_directions(self):
        for kind in (ZoneType.SUPPORT, ZoneType.RESISTANCE):
            with self.subTest(kind=kind):
                source, origin, incoming, current = self.setup_move(kind)
                self.assertIs(PreviousMoveResolver.resolve(current, origin, [source, origin]), incoming)
                self.assertEqual((current.previous_distance, current.previous_movement_time), (30, 10))
                self.assertIsNone(current.movement_energy)

    def test_latest_incoming_origin_and_broken_history(self):
        source, origin, incoming, current = self.setup_move()
        latest = movement(source.id, 12, 125, 15)
        InteractionCloser.close(latest, source, origin)
        source.interactions.insert(0, latest)
        source.state = ZoneState.BROKEN
        self.assertIs(PreviousMoveResolver.resolve(current, origin, [source]), latest)
        self.assertEqual((current.previous_distance, current.previous_movement_time), (25, 5))

    def test_unrelated_newer_move_is_excluded(self):
        source, origin, incoming, current = self.setup_move()
        other_destination = zone(3, ZoneType.SUPPORT, 95, 25)
        unrelated = movement(source.id, 12, 120, 22)
        InteractionCloser.close(unrelated, source, other_destination)
        source.interactions.append(unrelated)
        self.assertIs(PreviousMoveResolver.resolve(current, origin, [source]), incoming)

    def test_no_reference_resets_bootstrap(self):
        source, origin, incoming, current = self.setup_move()
        incoming.state = InteractionState.OPEN
        current.previous_distance = 99
        current.previous_movement_time = 99
        self.assertIsNone(PreviousMoveResolver.resolve(current, origin, [source]))
        self.assertEqual((current.previous_distance, current.previous_movement_time), (None, None))

    def test_same_type_is_excluded(self):
        source, origin, incoming, current = self.setup_move()
        source.type = origin.type
        self.assertIsNone(PreviousMoveResolver.resolve(current, origin, [source]))

    def test_invalid_measurements_do_not_mutate_current(self):
        for field, value in (("distance", 0), ("movement_time", 0), ("distance", float("nan"))):
            with self.subTest(field=field, value=value):
                source, origin, incoming, current = self.setup_move()
                setattr(incoming, field, value)
                with self.assertRaises(ValueError):
                    PreviousMoveResolver.resolve(current, origin, [source])
                self.assertEqual((current.previous_distance, current.previous_movement_time), (None, None))

    def test_wrong_origin_is_rejected(self):
        source, origin, incoming, current = self.setup_move()
        current.zone_id = source.id
        with self.assertRaises(ValueError):
            PreviousMoveResolver.resolve(current, origin, [source])

    def test_ambiguous_history_is_rejected(self):
        source, origin, incoming, current = self.setup_move()
        duplicate = movement(source.id, 12, 125, incoming.start_index)
        InteractionCloser.close(duplicate, source, origin)
        source.interactions.append(duplicate)
        with self.assertRaises(ValueError):
            PreviousMoveResolver.resolve(current, origin, [source])


if __name__ == "__main__":
    unittest.main()
