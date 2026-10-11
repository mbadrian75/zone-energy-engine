import unittest
from datetime import datetime, timedelta, timezone
from multi_timeframe_replay import ClosedBar, MultiTimeframeReplay

UTC = timezone.utc

def bar(tf, hour):
    return ClosedBar(tf, datetime(2020, 1, 1, tzinfo=UTC) + timedelta(hours=hour), 100, 102, 99, 101)

class FakeZoneEngine:
    def __init__(self):
        self.processed = {tf: [] for tf in ('H1', 'H4', 'D1')}
    def on_closed_bar(self, timeframe, candle):
        self.processed[timeframe].append(candle.closed_at)
    def snapshot(self, timeframe):
        return list(self.processed[timeframe])

class ReplayTests(unittest.TestCase):
    def test_only_closed_bars_and_equal_close_available(self):
        streams = {'H1': [bar('H1',h) for h in (1,2,3,4,5)],
                   'H4': [bar('H4',4),bar('H4',8)],
                   'D1': [bar('D1',24)]}
        points = list(MultiTimeframeReplay(streams, FakeZoneEngine()).run())
        self.assertEqual(len(points), 5)
        self.assertEqual(points[2].zones['H4'], [])
        self.assertEqual(points[3].zones['H4'], [bar('H4',4).closed_at])
        self.assertEqual(points[4].zones['H4'], [bar('H4',4).closed_at])
        self.assertEqual(points[4].zones['D1'], [])
        self.assertTrue(all(t <= p.at for p in points for t in sum((p.zones[k] for k in ('H1','H4','D1')), [])))

    def test_future_bar_does_not_affect_earlier_decisions(self):
        base = {'H1': [bar('H1',1),bar('H1',2)], 'H4': [], 'D1': []}
        future = {'H1': base['H1'], 'H4': [bar('H4',8)], 'D1': [bar('D1',24)]}
        a = list(MultiTimeframeReplay(base, FakeZoneEngine()).run())
        b = list(MultiTimeframeReplay(future, FakeZoneEngine()).run())
        self.assertEqual(a, b)

    def test_reject_unsorted_data(self):
        streams = {'H1': [bar('H1',2), bar('H1',1)], 'H4': [], 'D1': []}
        with self.assertRaises(ValueError):
            list(MultiTimeframeReplay(streams, FakeZoneEngine()).run())

    def test_reject_invalid_volume(self):
        with self.assertRaises(ValueError):
            ClosedBar("H1", datetime(2020,1,1,tzinfo=UTC),100,101,99,100,volume=-1)

    def test_reject_naive_timestamp(self):
        with self.assertRaises(ValueError):
            ClosedBar('H1', datetime(2020,1,1),100,101,99,100)

if __name__ == '__main__':
    unittest.main()
