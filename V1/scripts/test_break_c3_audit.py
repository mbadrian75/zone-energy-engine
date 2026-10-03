import unittest
from datetime import datetime,timedelta
from audit_replay_breaks import compare_c3
from zone_energy.models import Candle,Interaction,InteractionState,Zone,ZoneState,ZoneType
from zone_energy.replay.replay_engine import ReplayState


class C3AuditTests(unittest.TestCase):
    def fixture(self):
        # Actual ambiguous candle 124 is a support after a resistance origin.
        values = [(2666.595,2666.645,2662.074,2662.218),
                  (2662.164,2666.714,2660.268,2664.124),
                  (2664.234,2666.444,2662.068,2664.744)]
        candles = [Candle(datetime(2025,1,9)+timedelta(hours=i),*bar,0)
                   for i,bar in enumerate(values)]
        zone = Zone(2,ZoneType.SUPPORT,ZoneState.ACTIVE,2660,2661,2660.268,1)
        zone.interactions = [Interaction(3,2,InteractionState.OPEN,2660.268,1)]
        return {"candle_index":1,"origin_type":"resistance"},candles,ReplayState([zone],[])

    def test_break_c2_followed_by_valid_opposite_confirmation(self):
        row,candles,state = self.fixture()
        result = compare_c3(row,candles,state)
        self.assertEqual(result["c3_check"],"opposite_reaction_confirmed_next_candle")
        self.assertEqual(result["next_confirmed_pattern"],"support")
        self.assertEqual(result["valid_reactions_at_c2"],[{"zone_id":2,"interaction_id":3}])
        self.assertNotIn("c3_check",row)

    def test_pattern_is_not_equivalent_to_a_retained_reaction(self):
        row,candles,state = self.fixture()
        state.zones[0].interactions = []
        self.assertEqual(compare_c3(row,candles,state)["c3_check"],"opposite_pattern_without_retained_reaction")
        state.invalidated_reactions.append({"zone_id":2,"interaction_id":3,"reaction_index":1,
                                           "reaction_type":"support","break_index":4})
        self.assertEqual(compare_c3(row,candles,state)["c3_check"],"opposite_reaction_later_invalidated")

    def test_does_not_read_c3_beyond_checkpoint(self):
        row,candles,state = self.fixture()
        self.assertEqual(compare_c3(row,candles[:2],state)["c3_check"],"three_candle_window_unavailable")


if __name__ == "__main__":
    unittest.main()
