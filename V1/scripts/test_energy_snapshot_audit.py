import unittest
from copy import deepcopy
from audit_replay_breaks import EnergySnapshotAudit
from zone_energy.config import EngineConfig
from zone_energy.engine.market_energy_snapshot import MarketEnergySnapshotCalculator
from zone_energy.models import Interaction,InteractionState,Zone,ZoneState,ZoneType


class EnergyAuditTests(unittest.TestCase):
    def test_open_only_zero_and_finalized_energy_are_distinguished(self):
        config = EngineConfig()
        zone = Zone(126,ZoneType.RESISTANCE,ZoneState.ACTIVE,2938.275,2940.855,2940.855,876,
                    created_at_index=877)
        zone.interactions = [Interaction(244,126,InteractionState.OPEN,2940.855,876)]
        reports = []
        audit = EnergySnapshotAudit(MarketEnergySnapshotCalculator(config),config,126,879,reports)
        before = deepcopy(zone)
        snapshot = audit.capture([zone],879,5905)
        self.assertEqual(zone,before)
        self.assertEqual(snapshot.reference_for_break(126),(None,None))
        self.assertIsNone(reports[-1]["zero_reason"])
        self.assertEqual(reports[-1]["interactions"][0]["exclusion_reason"],"open_not_finalized")
        zone.interactions.insert(0,Interaction(240,126,InteractionState.CLOSED,2940.855,876,
                                             end_index=878,base_energy=5))
        audit.capture([zone],879,5905)
        self.assertGreater(reports[-1]["effective_zone_energy"],0)
        self.assertTrue(reports[-1]["interactions"][0]["included_in_sum"])


if __name__ == "__main__":
    unittest.main()
