"""Append-only, run-scoped MongoDB persistence for XAUUSD V2 replay results.

The existing xauusd_* collections and V1 checkpoints are never modified.
A failed or interrupted run is intentionally NOT resumed automatically: rerun
with a fresh run_id until an explicit state restoration mechanism exists.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

TIMEFRAMES = ("H1", "H4", "D1")
SCHEMA_VERSION = 1


def utc_naive(value: datetime) -> datetime:
    """MongoDB UTC datetime convention, without local-time ambiguity."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class MongoV2ResultRepository:
    """Persist immutable decisions and first-seen zone identity in three collections.

    Zone catalog: static identity/boundaries, once per (run, timeframe, zone).
    Snapshots: one per H1 close, containing *current* type/state/energy for all
    zones; these observations also constitute a per-zone temporal history.
    Runs: configuration, progress and status. No implicit resume on failure.
    """

    def __init__(self, *, client=None, mongo_uri="mongodb://localhost:27017/",
                 database="market_data"):
        if client is None:
            from pymongo import MongoClient
            client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
            self._owns_client = True
        else:
            self._owns_client = False
        self.client = client
        db = client[database]
        self.runs = db["zone_energy_v2_runs"]
        self.zones = db["zone_energy_v2_zones"]
        self.snapshots = db["zone_energy_v2_snapshots"]
        self._run_id = None
        self._status = None
        self._last_at = None
        self._seen_zones = set()
        self._count = 0

    def close(self):
        if self._owns_client:
            self.client.close()

    def begin_run(self, *, run_id: str, start: datetime, end: datetime,
                  year_candles: dict[str, int]) -> None:
        if self._run_id is not None:
            raise RuntimeError("A run is already open on this repository")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must not be empty")
        start_utc, end_utc = utc_naive(start), utc_naive(end)
        if start_utc >= end_utc:
            raise ValueError("start must precede end")
        if set(year_candles) != set(TIMEFRAMES) or any(
            type(year_candles[tf]) is not int or year_candles[tf] <= 0 for tf in TIMEFRAMES
        ):
            raise ValueError("Positive yearly candle counts required for H1, H4, D1")
        self.snapshots.create_index([("run_id", 1), ("decision_at", 1)], unique=True)
        self.zones.create_index([("run_id", 1), ("timeframe", 1), ("zone_id", 1)], unique=True)
        self.runs.insert_one({
            "_id": run_id, "schema_version": SCHEMA_VERSION, "symbol": "XAUUSD",
            "start": start_utc, "end": end_utc,
            "year_candles": dict(year_candles), "status": "running",
            "snapshot_count": 0, "last_decision_at": None,
            "started_at": datetime.now(timezone.utc).replace(tzinfo=None),
        })
        self._run_id = run_id
        self._status = "running"
        self._start = start_utc
        self._end = end_utc

    def _serialize(self, point):
        at = utc_naive(point.at)
        if not self._start <= at <= self._end:
            raise ValueError("Decision outside requested run interval")
        if self._last_at is not None and at <= self._last_at:
            raise ValueError("Decision timestamps must strictly increase")
        if set(point.zones) != set(TIMEFRAMES) or set(point.last_closed_at) != set(TIMEFRAMES):
            raise ValueError("Decision must include all three timeframes")
        closes = {tf: utc_naive(t) if t is not None else None
                  for tf, t in point.last_closed_at.items()}
        if closes["H1"] != at or any(t is not None and t > at for t in closes.values()):
            raise ValueError("Future or inconsistent completed-candle timestamp")
        new_zones = []
        tf_payload = {}
        for tf in TIMEFRAMES:
            state = point.zones[tf]
            rows = []
            local_seen = set()
            for zone in state["zones"]:
                zone_id = zone["zone_id"]
                if not isinstance(zone_id, str) or not zone_id.startswith(tf + ":"):
                    raise ValueError("Zone ID must be namespaced by timeframe")
                key = (tf, zone_id)
                if key in local_seen:
                    raise ValueError("Duplicate zone in one timeframe snapshot")
                local_seen.add(key)
                if key not in self._seen_zones:
                    new_zones.append({
                        "_id": f"{self._run_id}|{zone_id}",
                        "run_id": self._run_id, "symbol": "XAUUSD",
                        "timeframe": tf, "zone_id": zone_id,
                        "local_zone_id": zone["local_zone_id"],
                        "lower_price": zone["lower_price"],
                        "upper_price": zone["upper_price"],
                        "creation_index": zone["creation_index"],
                        "created_at_index": zone["created_at_index"],
                        "first_observed_at": at,
                    })
                rows.append({
                    "zone_id": zone_id,
                    "type": zone["type"], "state": zone["state"],
                    "interaction_count": zone["interaction_count"],
                    "effective_energy": zone["effective_energy"],
                })
            tf_payload[tf] = {
                "candle_index": state["candle_index"],
                "median_active_energy": state["median_active_energy"],
                "zones": rows,
            }
        snapshot = {
            "_id": f"{self._run_id}|{at.isoformat()}",
            "run_id": self._run_id, "symbol": "XAUUSD",
            "decision_at": at, "last_closed_at": closes,
            "timeframes": tf_payload,
        }
        return snapshot, new_zones

    def append_points(self, points: Iterable, *, batch_size: int = 25) -> int:
        if self._status != "running":
            raise RuntimeError("A running run is required before appending")
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        snapshots, new_zone_docs, pending_keys = [], [], set()
        count = 0
        for point in points:
            snapshot, zones = self._serialize(point)
            if snapshots and snapshot["decision_at"] <= snapshots[-1]["decision_at"]:
                raise ValueError("Decision timestamps must strictly increase")
            snapshots.append(snapshot)
            for zone in zones:
                key = (zone["timeframe"], zone["zone_id"])
                if key not in pending_keys:
                    new_zone_docs.append(zone)
                    pending_keys.add(key)
            if len(snapshots) >= batch_size:
                count += self._flush(snapshots, new_zone_docs, pending_keys)
                snapshots, new_zone_docs, pending_keys = [], [], set()
        if snapshots:
            count += self._flush(snapshots, new_zone_docs, pending_keys)
        return count

    def _flush(self, snapshots: list[dict], new_zones: list[dict], keys: set) -> int:
        # Catalog first: a stored snapshot never points to a missing zone.
        if new_zones:
            self.zones.insert_many(new_zones, ordered=True)
            self._seen_zones.update(keys)
        self.snapshots.insert_many(snapshots, ordered=True)
        n = len(snapshots)
        last_at = snapshots[-1]["decision_at"]
        result = self.runs.update_one({"_id": self._run_id, "status": "running"}, {
            "$inc": {"snapshot_count": n},
            "$set": {"last_decision_at": last_at},
        })
        if result.matched_count != 1:
            raise RuntimeError("Could not record run progress")
        self._last_at = last_at
        self._count += n
        return n

    def finish_run(self) -> int:
        if self._status != "running":
            raise RuntimeError("No running run to finish")
        if not self._count:
            raise ValueError("Cannot complete a run with zero decisions")
        result = self.runs.update_one({"_id": self._run_id, "status": "running"}, {
            "$set": {"status": "completed",
                     "finished_at": datetime.now(timezone.utc).replace(tzinfo=None)}
        })
        if result.matched_count != 1:
            raise RuntimeError("Run was not in running state")
        self._status = "completed"
        return self._count

    def fail_run(self, error: Exception) -> None:
        if self._status == "running":
            self.runs.update_one({"_id": self._run_id, "status": "running"}, {
                "$set": {"status": "failed", "error_type": type(error).__name__,
                         "failed_at": datetime.now(timezone.utc).replace(tzinfo=None)}
            })
            self._status = "failed"
