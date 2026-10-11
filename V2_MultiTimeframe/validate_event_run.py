"""Read-only validation gate for schema-3 runs, with schema-2 read support."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path

from mongo_event_repository import MongoEventRepository, MongoEventReader, TIMEFRAMES, unpack, code_fingerprint, apply_event, SCHEMA_VERSION


def require_validated_smoke(repository, run_id, year_counts):
    if not run_id:
        raise ValueError("Replays longer than 31 days require --validated-smoke-run-id")
    run = MongoEventReader(repository, run_id)._completed()
    if run["start"] != datetime(2025, 1, 1) or run["end"] != datetime(2025, 2, 1):
        raise ValueError("Validation requires the January 2025 smoke interval")
    if run["year_candles"] != year_counts or run.get("code_fingerprint") != code_fingerprint():
        raise ValueError("Smoke code/config differs; run a fresh smoke test")
    report = validate(repository, run_id, Path(__file__).with_name("v2-smoke-2025-01.jsonl"))
    if report["decisions"] != 504 or report["zones"] != 116:
        raise ValueError("January smoke totals mismatch")
    return report


def validate(repository, run_id, reference_path, *, schema_version=SCHEMA_VERSION):
    reader = MongoEventReader(repository, run_id, schema_version=schema_version)
    run = reader._completed()
    scope = reader.scope
    events = iter(repository.events.find(scope).sort("seq", 1))
    event = next(events, None)
    rows = {tf: {} for tf in TIMEFRAMES}
    seq = count = 0
    last_at = None
    last_event_order = None
    priority = {"D1": 0, "H4": 1, "H1": 2}
    compressed_bytes = raw_bytes = 0
    rejection_count = 0
    boundary_rejection_count = 0
    removal_count = revision_count = 0

    def consume_event(e):
        nonlocal seq, last_event_order, rejection_count, removal_count, revision_count
        nonlocal boundary_rejection_count
        order = (e["observed_at"], priority[e["timeframe"]])
        if e["seq"] != seq + 1 or (last_event_order is not None and order < last_event_order):
            raise ValueError("Event sequence/order mismatch")
        if not run["start"] <= e["observed_at"] <= run["end"]:
            raise ValueError("Event outside run interval")
        seq += 1
        last_event_order = order
        apply_event(rows, e)
        if e["kind"] == "reaction_rejected":
            rejection_count += 1
        if e["kind"] == "boundary_rejected":
            boundary_rejection_count += 1
        if e["kind"] == "removed":
            removal_count += 1
        if e["kind"] == "revised":
            revision_count += 1

    with Path(reference_path).open(encoding="utf-8") as reference:
        for snapshot in repository.snapshots.find(scope).sort("decision_seq", 1):
            count += 1
            if snapshot["decision_seq"] != count or (last_at is not None and snapshot["decision_at"] <= last_at):
                raise ValueError("Decision sequence/order mismatch")
            last_at = snapshot["decision_at"]
            if snapshot["event_seq"] < seq:
                raise ValueError("Event watermark regressed")
            while event is not None and event["seq"] <= snapshot["event_seq"]:
                if event["observed_at"] > last_at:
                    raise ValueError("Future event in H1 decision")
                consume_event(event)
                event = next(events, None)
            if seq != snapshot["event_seq"]:
                raise ValueError("Missing event tail")
            body = unpack(snapshot)
            if datetime.fromisoformat(body["decision_at"]).replace(tzinfo=None) != last_at:
                raise ValueError("Checkpoint timestamp mismatch")
            line = reference.readline()
            if not line or body != json.loads(line):
                raise ValueError(f"JSONL mismatch at decision {count}")
            for tf in TIMEFRAMES:
                expected_zones = body["timeframes"][tf]["zones"]
                order = [z["zone_id"] for z in expected_zones]
                if len(order) != len(set(order)) or set(order) != set(rows[tf]):
                    raise ValueError(f"Zone membership mismatch at decision {count}, {tf}")
                if [rows[tf][zid] for zid in order] != expected_zones:
                    raise ValueError(f"Event reconstruction mismatch at decision {count}, {tf}")
            raw_bytes += snapshot["raw_bytes"]
            compressed_bytes += len(snapshot["payload"])
        if reference.readline():
            raise ValueError("Reference has additional decisions")
    # Higher-timeframe closes after the final H1 decision are retained, but never
    # applied to that decision. Validate their sequence as well.
    while event is not None:
        consume_event(event)
        event = next(events, None)
    if count != run["decision_count"] or seq != run["total_event_count"]:
        raise ValueError("Run totals mismatch")
    if rejection_count != run.get("total_rejection_count", 0):
        raise ValueError("Rejection audit count mismatch")
    if boundary_rejection_count != run.get("total_boundary_rejection_count", 0):
        raise ValueError("Boundary rejection audit count mismatch")
    if removal_count != run.get("total_removal_count", 0) or revision_count != run.get("total_revision_count", 0):
        raise ValueError("Zone membership/revision totals mismatch")
    if not count or last_at != run["last_decision_at"]:
        raise ValueError("Invalid completion marker")
    last = repository.snapshots.find_one({**scope, "decision_seq": count})
    if last["event_seq"] != run["committed_event_seq"]:
        raise ValueError("Committed watermark mismatch")
    return {"run_id": run_id, "decisions": count, "events": seq,
            "zones": sum(len(z) for z in rows.values()), "all_decisions_match": True,
            "zero_distance_rejections": rejection_count,
            "zero_width_boundary_rejections": boundary_rejection_count,
            "zone_removals": removal_count, "zone_revisions": revision_count,
            "schema_version": schema_version,
            "all_event_states_match": True, "raw_bytes": raw_bytes,
            "compressed_bytes": compressed_bytes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--database", default="market_data")
    parser.add_argument("--schema-version", type=int, choices=(2, 3), default=SCHEMA_VERSION)
    args = parser.parse_args()
    repo = MongoEventRepository(mongo_uri=os.environ.get("ZONE_ENERGY_MONGO_URI", "mongodb://localhost:27017/"),
                                database=args.database)
    try:
        print(json.dumps(validate(repo, args.run_id, args.reference, schema_version=args.schema_version), indent=2))
    finally:
        repo.close()


if __name__ == "__main__":
    main()
