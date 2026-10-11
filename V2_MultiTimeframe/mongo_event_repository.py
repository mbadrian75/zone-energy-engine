"""Schema 2: closed-bar events and compressed H1 checkpoints, append only.

Only completed runs are public. A write error poisons the writer; there is no
retry/resume. Ordered inserts may leave partial batches. The run progress marker
advances only after every insert succeeds. A process kill leaves status running.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import zlib
from pathlib import Path

from mongo_result_repository import TIMEFRAMES, utc_naive as _utc_naive

SCHEMA_VERSION = 2
PREFIX = "zone_energy_v2_event_"
STATIC = ("zone_id", "local_zone_id", "lower_price", "upper_price",
          "creation_index", "created_at_index")
DYNAMIC = ("type", "state", "interaction_count", "effective_energy")


def utc_naive(value):
    stamp = _utc_naive(value)
    if stamp.microsecond % 1000:
        raise ValueError("Timestamp exceeds MongoDB millisecond precision")
    return stamp


def code_fingerprint():
    root = Path(__file__).resolve().parents[1]
    files = sorted((root / "V1" / "src").rglob("*.py")) + sorted((root / "V2_MultiTimeframe").glob("*.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def pack(value):
    raw = encode(value)
    payload = zlib.compress(raw, level=6)
    # Leave ample space for BSON metadata; fail before an oversized insert.
    if len(payload) > 15 * 1024 * 1024:
        raise ValueError("Compressed checkpoint exceeds safe BSON limit")
    return {"codec": "zlib-json-v1", "payload": payload,
            "sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw)}


def unpack(doc):
    if doc["codec"] != "zlib-json-v1":
        raise ValueError("Unsupported checkpoint codec")
    raw = zlib.decompress(doc["payload"])
    if len(raw) != doc["raw_bytes"] or hashlib.sha256(raw).hexdigest() != doc["sha256"]:
        raise ValueError("Checkpoint integrity mismatch")
    return json.loads(raw)


def apply_event(rows, event):
    tf, zid, after = event["timeframe"], event["zone_id"], event["after"]
    if tf not in TIMEFRAMES or not zid.startswith(tf + ":"):
        raise ValueError("Invalid event zone identity")
    if event["kind"] == "created":
        if zid in rows[tf] or set(after) != set(STATIC + DYNAMIC) or after["zone_id"] != zid:
            raise ValueError("Invalid or duplicate creation")
        changed = list(DYNAMIC)
    elif event["kind"] == "changed":
        if zid not in rows[tf] or set(after) != set(DYNAMIC):
            raise ValueError("Change precedes creation or changes static identity")
        changed = [k for k in DYNAMIC if rows[tf][zid][k] != after[k]]
    else:
        raise ValueError("Unsupported event kind")
    if not changed or changed != event["changed_fields"]:
        raise ValueError("Event changed_fields mismatch")
    encode(after)
    if event["kind"] == "created":
        rows[tf][zid] = deepcopy(after)
    else:
        rows[tf][zid].update(after)


class MongoEventRepository:
    def __init__(self, *, client=None, mongo_uri="mongodb://localhost:27017/",
                 database="market_data", event_batch_size=1000):
        if type(event_batch_size) is not int or event_batch_size <= 0:
            raise ValueError("event_batch_size must be positive")
        self.owns_client = client is None
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000,
                                 w="majority", j=True, wTimeoutMS=30000)
        self.client = client
        db = client[database]
        self.runs, self.events, self.snapshots = (
            db[PREFIX + name] for name in ("runs", "events", "snapshots"))
        # Enforce durability/primary reads even for a caller-supplied real client.
        if hasattr(self.runs, "with_options"):
            from pymongo import ReadPreference
            from pymongo.read_concern import ReadConcern
            from pymongo.write_concern import WriteConcern
            options = dict(write_concern=WriteConcern(w="majority", j=True, wtimeout=30000),
                           read_concern=ReadConcern("majority"), read_preference=ReadPreference.PRIMARY)
            self.runs, self.events, self.snapshots = (
                collection.with_options(**options)
                for collection in (self.runs, self.events, self.snapshots))
        self.run_id = None
        self.status = None
        self.event_batch_size = event_batch_size
        self.pending_events = []
        self.pending_snapshots = []
        self.seq = self.count = 0
        self.last_observation = self.last_decision = None
        self.observed_at = {tf: None for tf in TIMEFRAMES}
        self.states = {tf: {"candle_index": None, "median_active_energy": None,
                            "zones": []} for tf in TIMEFRAMES}

    def close(self):
        if self.owns_client:
            self.client.close()

    def _running(self):
        if self.status != "running":
            raise RuntimeError("A running, healthy writer is required")

    def _doc(self, identity, **fields):
        # Array identity avoids delimiter collisions in caller-provided run IDs.
        return {"_id": encode([SCHEMA_VERSION, self.run_id, identity]).decode(),
                "schema_version": SCHEMA_VERSION, "run_id": self.run_id, **fields}

    def begin_run(self, *, run_id, start, end, year_candles):
        if self.run_id is not None:
            raise RuntimeError("Writer already used")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id required")
        self.start, self.end = utc_naive(start), utc_naive(end)
        if self.start >= self.end:
            raise ValueError("start must precede end")
        if set(year_candles) != set(TIMEFRAMES) or any(
                type(n) is not int or n <= 0 for n in year_candles.values()):
            raise ValueError("Positive yearly counts required")
        scope = [("schema_version", 1), ("run_id", 1)]
        self.runs.create_index(scope, unique=True)
        self.events.create_index(scope + [("seq", 1)], unique=True)
        self.events.create_index(scope + [("zone_id", 1), ("seq", 1)])
        self.events.create_index(scope + [("observed_at", 1), ("seq", 1)])
        self.snapshots.create_index(scope + [("decision_at", 1)], unique=True)
        self.snapshots.create_index(scope + [("decision_seq", 1)], unique=True)
        # Set ownership only after claiming the run successfully. Duplicate begin
        # must never allow fail_run to change another writer's run.
        doc = {"_id": run_id, "run_id": run_id, "schema_version": SCHEMA_VERSION,
               "status": "running", "symbol": "XAUUSD", "start": self.start,
               "end": self.end, "year_candles": deepcopy(year_candles),
               "code_fingerprint": code_fingerprint(),
               "decision_count": 0, "committed_event_seq": 0,
               "started_at": datetime.now(timezone.utc).replace(tzinfo=None)}
        self.runs.insert_one(doc)
        self.run_id, self.status = run_id, "running"

    def _scope(self):
        return {"run_id": self.run_id, "schema_version": SCHEMA_VERSION}

    def _write_events(self):
        if self.pending_events:
            self.events.insert_many(self.pending_events, ordered=True)
            self.pending_events = []

    def observe(self, timeframe, at, state):
        self._running()
        try:
            self._observe(timeframe, at, state)
        except BaseException:
            self.status = "poisoned"
            raise

    def _observe(self, timeframe, at, state):
        stamp = utc_naive(at)
        if timeframe not in TIMEFRAMES or not self.start <= stamp <= self.end:
            raise ValueError("Invalid observation timeframe/interval")
        priority = {"D1": 0, "H4": 1, "H1": 2}
        order = (stamp, priority[timeframe])
        if self.last_observation is not None and order <= self.last_observation:
            raise ValueError("Observations must follow closed-bar order")
        encode(state)  # Reject NaN/Infinity before any writes.
        if set(state) != {"candle_index", "median_active_energy", "zones"}:
            raise ValueError("Unsupported timeframe state fields")
        index = state["candle_index"]
        previous_index = self.states[timeframe]["candle_index"]
        if type(index) is not int or index < 0 or (previous_index is not None and index <= previous_index):
            raise ValueError("Candle index must strictly increase")
        median = state["median_active_energy"]
        if median is not None and type(median) not in (int, float):
            raise ValueError("Invalid median energy")
        old = {z["zone_id"]: z for z in self.states[timeframe]["zones"]}
        new = {}
        events = []
        for zone in state["zones"]:
            zid = zone["zone_id"]
            if not isinstance(zid, str) or zid != f"{timeframe}:{zone['local_zone_id']}":
                raise ValueError("Zone ID must match timeframe and local ID")
            if zid in new or set(zone) != set(STATIC + DYNAMIC):
                raise ValueError("Duplicate zone or unsupported zone fields")
            if zone["type"] not in ("support", "resistance") or zone["state"] not in ("active", "broken"):
                raise ValueError("Invalid type/state")
            if type(zone["interaction_count"]) is not int or zone["interaction_count"] < 0:
                raise ValueError("Invalid interaction_count")
            if zone["lower_price"] > zone["upper_price"]:
                raise ValueError("Invalid boundaries")
            if any(type(zone[k]) not in (int, float) for k in ("lower_price", "upper_price")):
                raise ValueError("Non-numeric boundaries")
            if type(zone["local_zone_id"]) is not int or zone["local_zone_id"] <= 0:
                raise ValueError("Invalid local zone ID")
            if any(type(zone[k]) is not int for k in ("creation_index", "created_at_index")) or not (
                    0 <= zone["creation_index"] <= zone["created_at_index"] <= index):
                raise ValueError("Future or invalid zone creation index")
            if zone["effective_energy"] is not None and type(zone["effective_energy"]) not in (int, float):
                raise ValueError("Invalid effective energy")
            new[zid] = zone
            previous = old.get(zid)
            if previous and any(zone[k] != previous[k] for k in STATIC):
                raise ValueError("Static zone identity changed")
            changed = [k for k in DYNAMIC if previous is None or zone[k] != previous[k]]
            if changed:
                events.append(self._doc(self.seq + len(events) + 1,
                    seq=self.seq + len(events) + 1, timeframe=timeframe, zone_id=zid,
                    observed_at=stamp, candle_index=state["candle_index"],
                    kind="created" if previous is None else "changed",
                    changed_fields=changed,
                    after=deepcopy(zone) if previous is None else {k: zone[k] for k in DYNAMIC}))
        if old.keys() - new.keys():
            raise ValueError("Known zones cannot disappear")
        self.seq += len(events)
        self.states[timeframe] = deepcopy(state)
        self.observed_at[timeframe] = stamp
        self.last_observation = order
        # Bounded event batches even during long H1 gaps.
        for event in events:
            self.pending_events.append(event)
            if len(self.pending_events) >= self.event_batch_size:
                self._write_events()

    def append_points(self, points, *, batch_size=25):
        self._running()
        if type(batch_size) is not int or batch_size <= 0:
            raise ValueError("batch_size must be positive")
        n = 0
        initial_count = self.count
        try:
            for point in points:
                self._running()
                stamp = utc_naive(point.at)
                closes = {tf: utc_naive(t) if t is not None else None
                          for tf, t in point.last_closed_at.items()}
                if set(point.zones) != set(TIMEFRAMES) or set(closes) != set(TIMEFRAMES):
                    raise ValueError("All timeframes required")
                if not self.start <= stamp <= self.end or (self.last_decision is not None and stamp <= self.last_decision):
                    raise ValueError("Decision timestamps must strictly increase within interval")
                if closes["H1"] != stamp or any(t is not None and t > stamp for t in closes.values()):
                    raise ValueError("Future or inconsistent close")
                if closes != self.observed_at or point.zones != self.states:
                    raise ValueError("Decision differs from observed causal state")
                body = {"symbol": "XAUUSD", "decision_at": point.at.astimezone(timezone.utc).isoformat(),
                        "last_closed_at": {tf: t.replace(tzinfo=timezone.utc).isoformat() if t else None
                                           for tf, t in closes.items()}, "timeframes": deepcopy(point.zones)}
                self.pending_snapshots.append(self._doc(["decision", initial_count + n + 1],
                    decision_seq=initial_count + n + 1, decision_at=stamp,
                    event_seq=self.seq, **pack(body)))
                self.last_decision = stamp
                n += 1
                if len(self.pending_snapshots) >= batch_size:
                    self._flush()
            self._flush()
        except BaseException:
            self.status = "poisoned"
            raise
        return n

    def _flush(self):
        self._write_events()
        if not self.pending_snapshots:
            return
        self.snapshots.insert_many(self.pending_snapshots, ordered=True)
        last = self.pending_snapshots[-1]
        result = self.runs.update_one({"_id": self.run_id, "status": "running", **self._scope()},
            {"$set": {"decision_count": last["decision_seq"],
                      "committed_event_seq": last["event_seq"],
                      "last_decision_at": last["decision_at"]}})
        if result.matched_count != 1:
            raise RuntimeError("Run progress update failed")
        self.count = last["decision_seq"]
        self.pending_snapshots = []

    def finish_run(self):
        self._running()
        if not self.count:
            raise ValueError("Cannot complete zero decisions")
        try:
            self._flush()
            result = self.runs.update_one({"_id": self.run_id, "status": "running", **self._scope()},
                {"$set": {"status": "completed", "total_event_count": self.seq,
                          "finished_at": datetime.now(timezone.utc).replace(tzinfo=None)}})
            if result.matched_count != 1:
                raise RuntimeError("Completion marker failed")
        except BaseException:
            self.status = "poisoned"
            raise
        self.status = "completed"
        return self.count

    def fail_run(self, error):
        if self.run_id is not None and self.status in ("running", "poisoned"):
            self.status = "poisoned"
            result = self.runs.update_one({"_id": self.run_id, "status": "running", **self._scope()},
                {"$set": {"status": "failed", "error_type": type(error).__name__}})
            if result.matched_count == 1:
                self.status = "failed"


class MongoEventReader:
    def __init__(self, repository, run_id):
        self.repo = repository
        self.scope = {"run_id": run_id, "schema_version": SCHEMA_VERSION}

    def _completed(self):
        run = self.repo.runs.find_one(self.scope)
        if run is None or run["status"] != "completed":
            raise RuntimeError("Only completed schema-2 runs may be read")
        return run

    def reconstruct(self, at, *, from_events=False):
        run = self._completed()
        doc = self.repo.snapshots.find_one({**self.scope, "decision_at": utc_naive(at)})
        if doc is None or doc["decision_seq"] > run["decision_count"]:
            raise ValueError("No committed H1 decision at requested instant")
        body = unpack(doc)
        if from_events:
            rows = {tf: {} for tf in TIMEFRAMES}
            expected = 1
            for event in self.repo.events.find({**self.scope, "seq": {"$lte": doc["event_seq"]}}).sort("seq", 1):
                if event["seq"] != expected or event["observed_at"] > doc["decision_at"]:
                    raise ValueError("Missing or future event")
                expected += 1
                apply_event(rows, event)
            if expected - 1 != doc["event_seq"]:
                raise ValueError("Missing event tail")
            for tf in TIMEFRAMES:
                order = [z["zone_id"] for z in body["timeframes"][tf]["zones"]]
                if len(order) != len(set(order)) or set(order) != set(rows[tf]):
                    raise ValueError("Checkpoint zone membership differs from events")
                body["timeframes"][tf]["zones"] = [rows[tf][zid] for zid in order]
        return body
