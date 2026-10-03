import unittest
from datetime import datetime, timedelta
from export_replay_chart import render_chart
from zone_energy.models import Candle, Interaction, InteractionState, Zone, ZoneState, ZoneType


class ChartTests(unittest.TestCase):
    def test_actual_ohlc_ambiguous_pattern_and_accepted_reaction_are_distinct(self):
        start = datetime(2025, 1, 1)
        bars = [Candle(start + timedelta(hours=i), *values, 0) for i, values in enumerate(
            [(105, 110, 100, 106), (106, 115, 95, 105), (105, 111, 102, 110),
             (116, 120, 116, 119)])]
        zone = Zone(19, ZoneType.RESISTANCE, ZoneState.BROKEN, 108, 112, 110, 0)
        move = Interaction(45, 19, InteractionState.OPEN, 115, 1)
        zone.interactions = [move]
        page = render_chart(bars, [zone], zone, move, 3, 0, 3)
        self.assertIn("O=106 H=115 L=95 C=105", page)
        self.assertIn("Ambiguous high AND low: no previous reaction at 2", page)
        self.assertIn("zone 19, interaction 45", page)
        self.assertIn("Origin breaks: 3", page)
        self.assertEqual(page.count("<svg "), 1)
        self.assertEqual(page.count("</svg>"), 1)

    def test_window_must_contain_start_and_break(self):
        with self.assertRaises(ValueError):
            render_chart([], [], None, Interaction(1, 1, InteractionState.OPEN, 100, 1), 2, 0, 3)


if __name__ == "__main__":
    unittest.main()
