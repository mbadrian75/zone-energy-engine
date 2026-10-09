import unittest
from summarize_replay_energy import distribution,summarize
from test_outgoing_c2_breaks import fixture


class EnergySummaryTests(unittest.TestCase):
    def test_unknown_zero_and_percentiles(self):
        report = distribution([None,0,10,20])
        self.assertEqual((report["undefined"],report["zero"],report["median"]),(1,1,10))
        self.assertAlmostEqual(report["p95"],19)
        self.assertIsNone(distribution([])["max"])
        with self.assertRaises(ValueError):
            distribution([float("inf")])

    def test_summary_keeps_break_and_origin_identity(self):
        engine,bars,_ = fixture()
        engine.process(bars[2])
        engine.process(bars[3])
        report = summarize(engine.state.zones,engine.config,125,5905)
        self.assertEqual(report["top_breaks"][0]["broken_zone_id"],19)
        self.assertEqual(report["top_breaks"][0]["interaction_id"],49)
        self.assertEqual(report["final_zone_energy"]["total"],2)


if __name__ == "__main__":
    unittest.main()
