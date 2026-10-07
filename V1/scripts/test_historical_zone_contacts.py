import unittest
from copy import deepcopy
from datetime import datetime
from audit_replay_breaks import zone_contacts
from zone_energy.models import Candle,Zone,ZoneState,ZoneType
from zone_energy.replay.replay_engine import ReplayState


class HistoricalContactsTests(unittest.TestCase):
    def test_historical_roles_wicks_and_creation_availability(self):
        active = Zone(1,ZoneType.SUPPORT,ZoneState.ACTIVE,100,110,100,1,created_at_index=2)
        broken = Zone(2,ZoneType.RESISTANCE,ZoneState.BROKEN,108,112,112,2,created_at_index=3)
        future = Zone(3,ZoneType.SUPPORT,ZoneState.ACTIVE,100,110,100,9,created_at_index=10)
        state = ReplayState([active,broken,future],[])
        before = deepcopy(state)
        candle = Candle(datetime(2025,1,1),113,115,105,113,0)
        report = zone_contacts(state,candle,5)
        rows = report["contacted_zones_before_processing"]
        self.assertEqual([row["zone_id"] for row in rows],[1,2])
        self.assertTrue(rows[0]["contains_low"])
        self.assertFalse(rows[1]["contains_high"])
        self.assertFalse(rows[1]["contains_low"])
        self.assertEqual(rows[1]["state_before_candle"],"broken")
        self.assertEqual(rows[0]["close_side"],"above")
        self.assertEqual(state,before)


if __name__ == "__main__":
    unittest.main()
