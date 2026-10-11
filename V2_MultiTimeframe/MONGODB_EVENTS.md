# MongoDB Event-Based V2 (schema_version=2)

For V1 replay failures, `diagnostics/diagnose_replay.py` repeats the same causal
replay in read-only mode and saves a fresh local JSON report with exact traceback
context. It never writes MongoDB data or changes engine behavior. Its placement
under diagnostics/ leaves the production engine fingerprint unchanged. Use the
same start/end and yearly counts as the failed run, and a new `--output` path.

Opt in with `--storage mongodb-events`. JSONL and the existing `--storage
mongodb` schema-1 implementation remain available. No V1 file, market-data
collection, or legacy result collection is altered. Only these collections are used:

| Collection | Content |
| --- | --- |
| `zone_energy_v2_event_runs` | Run claim, configuration, code fingerprint, progress and completion/failure marker |
| `zone_energy_v2_event_events` | Creation and every observed change to type, state, interaction_count, effective_energy |
| `zone_energy_v2_event_snapshots` | Zlib-compressed JSON at each H1 decision, SHA-256, event cutoff and decision sequence |

## Causal contract

The unchanged V1 engine processes one closed candle at a time. The V2 observer
samples the resulting zone state after **each** D1/H4/H1 closed candle, including
higher-timeframe closes in H1 gaps. At equal timestamps, D1 then H4 then H1 are
processed. These are closed-candle observations, not internal intermediate
assignments during a V1 `process()` call or intrabar/tick changes. Per-candle
energy decay produces events whenever the exact value changes. Undefined energy
remains null. Interaction counts may decrease when V1 discards provisional reactions;
such changes are recorded exactly rather than treated as cumulative counters.

Creation events contain complete static identity/boundaries and initial dynamic
state. Later events contain the four dynamic fields and the exact changed-field
list. Unchanged zones generate no events. All known zones, including broken
ones, remain in state. Static identity changes, disappearing zones, future
creation indexes, malformed states, NaN/Infinity, unordered closes, and
sub-millisecond timestamps are rejected.

Each H1 checkpoint contains the complete causal decision, all zone boundaries,
zone ordering and exact numeric values. Compression is lossless. Its event_seq
is captured before future candles are fed. Missing H1 candles do not generate
invented snapshots. Higher-timeframe events after the final H1 decision may be
retained, but are excluded from that decision's cutoff.

`MongoEventReader(repo, run_id).reconstruct(aware_utc_h1_time)` reads the exact
compressed checkpoint. `from_events=True` independently replays zone creation
and changes through that decision's event cutoff; zone ordering and timeframe summary metadata
comes from the checkpoint. An instant without an H1 decision is rejected.
Readers accept only completed schema-2 runs. Reading and validation perform no
inserts, updates, index creation or cleanup.

## Identity, batching and crash semantics

Every document and query is scoped by schema_version and run_id. Unique indexes
cover runs (schema/run), events (schema/run/seq), and snapshots
(schema/run/decision_at and schema/run/decision_seq). Secondary indexes support
zone history and observation-time queries. Event/snapshot IDs use JSON arrays
to prevent run-ID delimiter collisions.

The writer claims a fresh run using insert_one. Duplicate claims fail without
changing the existing run. Events/snapshots use insert only: no upsert, replace,
delete or update. Only the claimed run's progress/status changes. Defaults are
1,000 events per event batch and 25 H1 checkpoints per snapshot batch. Events
can flush during H1 gaps. The driver splits wire batches. Individual compressed
checkpoints larger than 15 MiB fail before insertion.

Real collections enforce majority, journaled writes with a 30-second
write-concern timeout and primary majority reads. Cross-collection writes are
**not transactional**; standalone MongoDB and replica sets are supported.
Events insert first, checkpoints second, progress advances last. Ordered writes
can leave partial batches. Any observer, iterator, insert or marker error poisons
the writer, prohibiting subsequent append/finish. Best-effort fail_run records
only the error class. A hard kill may leave status running. Neither failed nor
running runs can be consumed. Only an acknowledged completion marker publishes
the run. An ambiguous acknowledgement requires inspection of the run, never
write retries or ID reuse. There is no resume, rollback, auto-delete or overwrite.
Replay from the beginning with a new run_id. Database administrators can still
alter documents; use suitable writer/read-only consumer permissions.

MongoDB semantics: [write concern](https://www.mongodb.com/docs/manual/reference/write-concern/)
and [ordered inserts](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/crud/insert/).

## Validation before long replay

The checked-in `v2-smoke-2025-01.jsonl` contains 504 January H1 decisions and 116
zones across all timeframes. Offline equivalence feeds its observations through
the writer and compares every complete checkpoint and reconstructed zone.
JSONL alone cannot establish intermediate H4/D1 changes in H1 gaps. Separate
observer integration tests cover gaps, equal-time ordering, future exclusion,
terminal higher-timeframe events and the real V1 engine. Live MongoDB contract
tests are opt-in and retain fresh run documents in only the new collections.

`validate_event_run.py` streams the stored run once, checking full JSONL equality
at every H1 decision, exact zone reconstruction from events, checksums, contiguous
sequences, monotonic timestamps/cutoffs, no future events, run totals and final
committed marker. Any mismatch produces a nonzero exit code.

Event-mode replay longer than 31 days requires `--validated-smoke-run-id`.
Before claiming a new long run, the runner revalidates the completed January run
against JSONL and checks identical source-code fingerprint and year-candle
counts. Changes to V1/V2 Python source require a fresh smoke. Legacy modes are
unaffected. This validates storage/causality, not trading profitability or all
historical market data. Check full-history coverage and timestamp convention
separately before the sixteen-year replay.

## Windows Server / PowerShell

Run from the repository root using the server's existing virtual environment.
If needed, create `.venv` first. PyMongo in `V1/requirements.txt` is the only
external dependency; V1 itself is not modified.

```powershell
git fetch origin
if ($LASTEXITCODE -ne 0) { throw 'fetch failed' }
git switch feature/v2-mongodb-events
if ($LASTEXITCODE -ne 0) { throw 'switch failed' }
$taskPython = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $taskPython -m pip install -r .\V1\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'dependency installation failed' }
# Omit when the default localhost:27017 URI is correct.
$env:ZONE_ENERGY_MONGO_URI = 'mongodb://localhost:27017/'
& .\V2_MultiTimeframe\smoke_event_mongo.ps1 -PythonPath $taskPython -Database market_data
```

The script stops on failure. It runs unit/equivalence and live MongoDB contract
tests, replays actual January market data through V1, then validates the stored
run against the checked-in reference. It prints `VALIDATED_SMOKE_RUN_ID=...`
only after all stages pass. Expect 504 decisions, 116 zones,
all_decisions_match=true and all_event_states_match=true. Real replay event counts
can exceed offline-fixture counts when intermediate higher-timeframe observations
occur between H1 decisions. Market data are read only. No sixteen-year replay
is started by the smoke script.

To repeat read-only validation, substitute the printed ID:

```powershell
& $taskPython .\V2_MultiTimeframe\validate_event_run.py `
    --database market_data --run-id '<VALIDATED_SMOKE_RUN_ID>' `
    --reference .\V2_MultiTimeframe\v2-smoke-2025-01.jsonl
if ($LASTEXITCODE -ne 0) { throw 'validation failed; do not start long replay' }
```

After checking coverage, add `--validated-smoke-run-id '<VALIDATED_SMOKE_RUN_ID>'`
to the long replay command, with `--storage mongodb-events`, a new run ID and
the same yearly candle configuration. No long-history start/end dates are assumed.
