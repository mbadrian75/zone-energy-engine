import unittest
from types import SimpleNamespace

from diagnostics.diagnose_replay import failure_context
from zone_energy.engine.interaction_closer import InteractionCloser
from zone_energy.models import Interaction, InteractionState, ZoneType


class FailureContextTests(unittest.TestCase):
    def test_zero_distance_reports_actual_endpoint_and_preserves_open_move(self):
        interaction = Interaction(id=7, zone_id=1, state=InteractionState.OPEN,
                                  start_price=100.0, start_index=3)
        origin = SimpleNamespace(id=1, type=ZoneType.SUPPORT)
        endpoint = SimpleNamespace(id=2, type=ZoneType.RESISTANCE,
                                   creation_extreme=100.0, creation_index=8)
        try:
            InteractionCloser.close(interaction, origin, endpoint)
        except ValueError as error:
            report = failure_context(error)
        else:
            self.fail("Expected unchanged V1 to reject zero distance")
        self.assertEqual(report["error"], "Interaction distance must be greater than zero")
        self.assertEqual(report["distance"], 0)
        self.assertEqual(report["movement_time"], 5)
        self.assertEqual(report["end_price"], 100.0)
        self.assertEqual(report["interaction"]["id"], 7)
        self.assertEqual(report["interaction"]["state"], "open")
        self.assertEqual(interaction.state, InteractionState.OPEN)
        self.assertIsNone(interaction.distance)


if __name__ == "__main__":
    unittest.main()
