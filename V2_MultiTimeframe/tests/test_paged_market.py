import unittest
from datetime import datetime, timedelta
from market_streams import paged_candles


class Cursor:
    def __init__(self, rows):
        self.rows, self.closed = rows, False
    def sort(self, field, direction):
        self.rows = sorted(self.rows, key=lambda row: row[field])
        return self
    def limit(self, count):
        self.rows = self.rows[:count]
        return self
    def __iter__(self):
        return iter(self.rows)
    def close(self):
        self.closed = True


class Market:
    def __init__(self, stamps):
        self.rows = [{"datetime": stamp} for stamp in stamps]
        self.cursors = []
    def _get_collection(self, timeframe):
        return self
    def find(self, query):
        bounds = query["datetime"]
        rows = [row for row in self.rows if row["datetime"] < bounds["$lt"]
                and (row["datetime"] >= bounds["$gte"] if "$gte" in bounds
                     else row["datetime"] > bounds["$gt"])]
        cursor = Cursor(rows)
        self.cursors.append(cursor)
        return cursor
    def _document_to_candle(self, row):
        assert all(cursor.closed for cursor in self.cursors)
        return row["datetime"]


class PagedMarketTests(unittest.TestCase):
    def test_pages_match_stream_and_close_before_processing(self):
        start = datetime(2025, 1, 1)
        stamps = [start + timedelta(hours=i) for i in range(11)]
        market = Market(stamps)
        actual = list(paged_candles(market, "H1", start, stamps[-1], page_size=3))
        self.assertEqual(actual, stamps[:-1])
        self.assertEqual(len(market.cursors), 4)
    def test_duplicate_at_page_boundary_fails_before_yield(self):
        start = datetime(2025, 1, 1)
        market = Market([start, start + timedelta(hours=1), start + timedelta(hours=1)])
        with self.assertRaisesRegex(ValueError, "unique"):
            next(paged_candles(market, "H1", start, start + timedelta(days=1), page_size=2))
        self.assertTrue(market.cursors[0].closed)
    def test_empty_and_invalid(self):
        start = datetime(2025, 1, 1)
        self.assertEqual(list(paged_candles(Market([]), "D1", start, start + timedelta(days=1))), [])
        with self.assertRaises(ValueError):
            list(paged_candles(Market([]), "D1", start, start, page_size=0))
