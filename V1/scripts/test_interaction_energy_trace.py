import unittest
from copy import deepcopy
from trace_replay_interaction import interaction_report
from test_outgoing_c2_breaks import fixture


class EnergyTraceTests(unittest.TestCase):
    def test_break_inputs_and_history_are_reported_without_mutation(self):
        engine,bars,_ = fixture()
        engine.process(bars[2])
        engine.process(bars[3])
        before = deepcopy(engine.state)
        report = interaction_report(engine.state,49)
        self.assertEqual(report["interaction"]["breaks"][0]["broken_zone_id"],19)
        self.assertEqual(report["broken_zone_histories"][0]["retained_movements_ending_by_break"][0]["base_energy"],5)
        self.assertEqual(engine.state,before)
        with self.assertRaises(ValueError):
            interaction_report(engine.state,999)


if __name__ == "__main__":
    unittest.main()
