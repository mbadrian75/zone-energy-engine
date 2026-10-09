"""Validate HistData M1 ZIP files and append candles to market_data."""
import argparse
import csv
from datetime import datetime, timedelta
import io
import json
import math
import os
from pathlib import Path
import sys
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))

PERIODS = {"M1":1,"M5":5,"M15":15,"M30":30,"H1":60,"H4":240,"D1":1440}
COLLECTIONS = {tf:f"xauusd_{tf.lower()}" for tf in PERIODS}
PRICE_FIELDS = ("open","high","low","close","volume")


def read_minutes(folder, year, policy):
    minutes, conflicts, excluded = {}, [], set()
    raw_count = identical = 0
    files = sorted(Path(folder).glob("*.zip"))
    if not files:
        raise ValueError("No ZIP files found")
    for archive in files:
        with zipfile.ZipFile(archive) as bundle:
            members = sorted(n for n in bundle.namelist() if n.lower().endswith(".csv"))
            if not members:
                raise ValueError(f"No CSV in {archive.name}")
            for member in members:
                with bundle.open(member) as stream:
                    for line, cells in enumerate(csv.reader(io.TextIOWrapper(stream,encoding="utf-8-sig"),delimiter=";"),1):
                        if len(cells) != 6:
                            raise ValueError(f"Invalid row: {archive.name}:{line}")
                        stamp = datetime.strptime(cells[0],"%Y%m%d %H%M%S")
                        prices = tuple(map(float,cells[1:]))
                        op,high,low,close,volume = prices
                        if (stamp.year != year or stamp.second or
                            not all(math.isfinite(v) for v in prices) or volume < 0 or
                            not low <= min(op,close) <= max(op,close) <= high):
                            raise ValueError(f"Invalid M1 candle: {archive.name}:{line}")
                        raw_count += 1
                        previous = minutes.get(stamp)
                        if previous is not None:
                            if previous == prices:
                                identical += 1
                            else:
                                conflicts.append({"datetime":stamp.isoformat(),"file":archive.name,
                                                  "line":line,"previous":previous,"incoming":prices})
                                if policy == "last":
                                    minutes[stamp] = prices
                                elif policy == "skip":
                                    excluded.add(stamp)
                            continue
                        minutes[stamp] = prices
    if policy == "skip":
        for stamp in excluded:
            minutes.pop(stamp,None)
    report = {"files":len(files),"raw_records":raw_count,"unique_minutes":len(minutes),
              "identical_duplicates":identical,"conflicting_records":len(conflicts),
              "conflicting_timestamps":len({c['datetime'] for c in conflicts}),
              "conflict_policy":policy,"first":min(minutes).isoformat(),"last":max(minutes).isoformat()}
    return minutes,report,conflicts


def aggregate(minutes, timeframe):
    period = PERIODS[timeframe]
    buckets = {}
    for stamp, values in sorted(minutes.items()):
        midnight = stamp.replace(hour=0,minute=0,second=0,microsecond=0)
        start = midnight + timedelta(minutes=((stamp.hour*60+stamp.minute)//period)*period)
        op,high,low,close,volume = values
        if start not in buckets:
            buckets[start] = {"datetime":start,"open":op,"high":high,"low":low,
                              "close":close,"volume":volume,"source_minutes":1}
        else:
            row = buckets[start]
            row.update(high=max(row["high"],high),low=min(row["low"],low),close=close,
                       volume=row["volume"]+volume,source_minutes=row["source_minutes"]+1)
    return list(buckets.values())


def preflight(collection, rows):
    by_time = {r["datetime"]:r for r in rows}
    existing = set()
    for old in collection.find({"datetime":{"$gte":min(by_time),"$lte":max(by_time)}}):
        stamp = old["datetime"]
        if stamp in existing:
            raise ValueError(f"Duplicate MongoDB datetime in {collection.name}: {stamp}")
        existing.add(stamp)
        if stamp not in by_time:
            raise ValueError(f"Existing candle absent from chosen source in {collection.name}: {stamp}")
        if any(float(old.get(k,0)) != by_time[stamp][k] for k in PRICE_FIELDS):
            raise ValueError(f"Existing candle differs in {collection.name}: {stamp}; no overwrite performed")
    return len(existing)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",required=True)
    parser.add_argument("--year",type=int,default=2026)
    parser.add_argument("--on-conflict",choices=("error","first","last","skip"),default="error")
    parser.add_argument("--database",default="market_data")
    parser.add_argument("--write",action="store_true",help="Append to MongoDB; default validates files only")
    parser.add_argument("--report",default="histdata-import-report.json")
    parser.add_argument("--conflicts",default="histdata-conflicts.json")
    args = parser.parse_args()
    minutes,report,conflicts = read_minutes(args.input,args.year,args.on_conflict)
    Path(args.conflicts).write_text(json.dumps(conflicts,indent=2),encoding="utf-8")
    rows = {tf:aggregate(minutes,tf) for tf in PERIODS}
    report["timeframes"] = {tf:{"count":len(items),"first":items[0]["datetime"].isoformat(),
        "last":items[-1]["datetime"].isoformat(),"last_source_minutes":items[-1]["source_minutes"]}
        for tf,items in rows.items()}
    report.update(written=False,time_alignment="HistData timestamps unchanged; calendar buckets anchored at midnight; no gap filling")
    def save():
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    save()
    if conflicts and args.on_conflict == "error":
        raise ValueError(f"{len(conflicts)} conflicting records; choose an explicit on-conflict policy. Reports saved; no DB writes")
    if args.write:
        from pymongo import MongoClient,UpdateOne
        client = MongoClient(os.environ.get("ZONE_ENERGY_MONGO_URI","mongodb://localhost:27017/"),serverSelectionTimeoutMS=5000)
        try:
            client.admin.command("ping")
            db = client[args.database]
            # Validate every timeframe before inserting any candle.
            for tf,items in rows.items():
                count = preflight(db[COLLECTIONS[tf]],items)
                report["timeframes"][tf]["existing_identical"] = count
            for tf in rows:
                collection = db[COLLECTIONS[tf]]
                if not any(list(info["key"]) == [("datetime",1)] and info.get("unique")
                           for info in collection.index_information().values()):
                    collection.create_index("datetime",unique=True,name="histdata_datetime_unique")
            report["write_status"] = "in_progress"
            save()
            for tf,items in rows.items():
                collection = db[COLLECTIONS[tf]]
                inserted = 0
                for start in range(0,len(items),2000):
                    operations = [UpdateOne({"datetime":row["datetime"]},{"$setOnInsert":row},upsert=True)
                                  for row in items[start:start+2000]]
                    inserted += collection.bulk_write(operations,ordered=True).upserted_count
                if preflight(collection,items) != len(items):
                    raise ValueError(f"Post-import count differs for {tf}")
                report["timeframes"][tf]["inserted"] = inserted
                save()
                print(f"{tf}: {len(items)} candles verified; {inserted} inserted",flush=True)
            report.update(written=True,write_status="complete")
            save()
        finally:
            client.close()
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)


if __name__ == "__main__":
    main()
