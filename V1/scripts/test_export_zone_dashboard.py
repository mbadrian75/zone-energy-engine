import json
import unittest
from copy import deepcopy
from export_zone_dashboard import dashboard_data,render_dashboard
from zone_energy.config import EngineConfig
from zone_energy.models import Zone,ZoneType,ZoneState,Interaction,InteractionState


class DashboardTests(unittest.TestCase):
    def test_independent_decay_open_and_unknown_are_preserved_without_mutation(self):
        zone = Zone(1,ZoneType.SUPPORT,ZoneState.ACTIVE,99,101,100,0,created_at_index=1)
        zone.interactions = [Interaction(1,1,InteractionState.CLOSED,100,0,end_index=10,base_energy=10),
            Interaction(2,1,InteractionState.CLOSED,100,500,end_index=510,base_energy=20),
            Interaction(3,1,InteractionState.CLOSED,100,800,end_index=810,base_energy=None),
            Interaction(4,1,InteractionState.OPEN,100,900)]
        unknown = Zone(2,ZoneType.RESISTANCE,ZoneState.BROKEN,109,111,110,1,created_at_index=2)
        before = deepcopy([zone,unknown])
        bars = [{'index':1000,'datetime':'2025-01-01','open':100,'high':110,'low':99,'close':105}]
        report = dashboard_data([zone,unknown],bars,EngineConfig(),1000,1000,'run')
        self.assertAlmostEqual(report['zones'][0]['energy'], .5+20*(.05**.5))
        self.assertEqual([m['age'] for m in report['zones'][0]['interactions']],[1000,500,200,100])
        self.assertIsNone(report['zones'][0]['interactions'][-1]['contribution'])
        self.assertIsNone(report['zones'][1]['energy'])
        self.assertEqual(report['open_move']['interaction_id'],4)
        self.assertEqual([zone,unknown],before)

    def test_embedded_data_cannot_close_script(self):
        report={'run_id':'</script><script>alert(1)</script>','zones':[]}
        html=render_dashboard(report)
        self.assertNotIn(report['run_id'],html)
        payload=html.split('<script id="data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(payload),report)

    def test_multiple_open_moves_are_rejected(self):
        zone=Zone(1,ZoneType.SUPPORT,ZoneState.ACTIVE,99,101,100,0)
        zone.interactions=[Interaction(i,1,InteractionState.OPEN,100,i) for i in (1,2)]
        with self.assertRaisesRegex(ValueError,'multiple OPEN'):
            dashboard_data([zone],[{'index':10}],EngineConfig(),10,1000,'run')


if __name__ == '__main__':
    unittest.main()
