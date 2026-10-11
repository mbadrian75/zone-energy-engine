# MongoDB storage for Zone Energy V2

V2 supports --storage mongodb in run_v1_multitimeframe.py. JSONL output (--storage jsonl --output PATH) remains the default for backward compatibility. Mongo mode writes only three new collections inside the existing market_data database:

| Collection | Purpose |
| --- | --- |
| zone_energy_v2_runs | _id = run_id; configuration, progress, and status (running, completed, failed) |
| zone_energy_v2_zones | One document per (run_id, timeframe, zone_id) with stable zone boundaries and formation indices |
| zone_energy_v2_snapshots | One document per (run_id, decision_at) containing the currently known type, state, interaction count and energy of every H1/H4/D1 zone |

Snapshot data include ALL known zones (ACTIVE and BROKEN). This supports historical role changes and later interactions. Undefined V1 energy remains null, not zero. Zone IDs are timeframe-qualified (H1:1, H4:1). UTC instants are stored as MongoDB datetimes. Stable zone boundaries are stored only in the catalog rather than in each hourly snapshot. Reconstruct a zone's evolving state and energy from snapshots for the same run ordered by decision_at.

## First Windows Server smoke test

Run inside V2_MultiTimeframe after pulling changes and running tests:

~~~powershell
& ..\.venv\Scripts\python.exe .\run_v1_multitimeframe.py --start 2025-01-01 --end 2025-02-01 --year-candles-h1 5933 --year-candles-h4 1601 --year-candles-d1 313 --storage mongodb --run-id v2-smoke-2025-01-001
~~~

The 2024 H1/H4/D1 candle counts above are appropriate only for a 2025 smoke test. Using future-observed 2024 counts retrospectively for training or evaluation in 2010-2023 would introduce hindsight into decay calibration. An ex-ante calibration policy must be chosen before a full replay.

Results are written in batches (default 25 H1 decisions). Duplicate run IDs and decision timestamps are rejected; existing completed results are never replaced. A failed or interrupted run can leave partial data marked non-completed. Resume is NOT implemented; use a NEW run ID and replay from scratch. Writes across the three collections are NOT cross-collection transactional. Downstream models must use only completed runs.

Legacy xauusd_* candle collections and V1 checkpoint collections remain untouched.

## Tests

~~~powershell
& ..\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

The MongoDB repository unit tests use a fake client and never touch a real database. Real MongoDB write/read integration remains to be tested on Windows Server.

Before the 2010-2025 backfill: confirm HistData timestamp and session interpretation, agree on historically valid decay calibration, plan for Mongo storage growth, and replay from the 2010 beginning for complete 2025 zone history.
