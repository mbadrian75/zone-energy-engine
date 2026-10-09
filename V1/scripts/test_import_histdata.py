import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from import_histdata import read_minutes,aggregate,preflight


class HistDataTests(unittest.TestCase):
    def load(self,policy='last'):
        with tempfile.TemporaryDirectory() as folder:
            with zipfile.ZipFile(Path(folder)/'sample.zip','w') as archive:
                archive.writestr('sample.csv','20260101 180100;10;12;9;11;0\n'
                    '20260101 180000;9;11;8;10;0\n'
                    '20260101 180100;11;14;10;13;0\n'
                    '20260101 180100;11;14;10;13;0\n')
            return read_minutes(folder,2026,policy)

    def test_last_record_and_chronological_aggregation(self):
        minutes,report,conflicts=self.load()
        self.assertEqual(report['raw_records'],4)
        self.assertEqual(report['unique_minutes'],2)
        self.assertEqual(report['conflicting_records'],1)
        self.assertEqual(report['identical_duplicates'],1)
        row=aggregate(minutes,'H1')[0]
        self.assertEqual((row['open'],row['high'],row['low'],row['close']),(9,14,8,13))
        self.assertEqual(row['source_minutes'],2)
        self.assertEqual(aggregate(minutes,'H4')[0]['datetime'],datetime(2026,1,1,16))
        self.assertEqual(aggregate(minutes,'D1')[0]['datetime'],datetime(2026,1,1))

    def test_skip_removes_entire_conflicting_timestamp(self):
        minutes,_,_=self.load('skip')
        self.assertEqual(list(minutes),[datetime(2026,1,1,18)])

    def test_existing_different_price_or_duplicate_is_rejected(self):
        rows=aggregate(self.load()[0],'M1')
        class Collection:
            name='test'
            def __init__(self,docs):self.docs=docs
            def find(self,query):return self.docs
        self.assertEqual(preflight(Collection(rows),rows),2)
        wrong=dict(rows[0],close=999)
        with self.assertRaisesRegex(ValueError,'differs'):
            preflight(Collection([wrong]),rows)
        with self.assertRaisesRegex(ValueError,'Duplicate MongoDB'):
            preflight(Collection([rows[0],rows[0]]),rows)


if __name__=='__main__':
    unittest.main()
