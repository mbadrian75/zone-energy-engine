# MongoDB Event-Based V2 (schema_version=3)

## Observed zone membership and revisions

V1's origin-invalidation replay restores an earlier engine seed and rebuilds
its reaction window. A formerly visible zone can disappear, reappear or be
replaced under the same local ID. The writer records the engine's actual state
at each observation, rather than assuming every formerly visible ID stays
present forever. `removed` events contain the full prior zone and null after;
`revised` events contain full before/after states when boundaries or creation
identity change. A removed local ID can subsequently get another `created`
event. No prior event, snapshot or market record is updated or deleted.

The reader verifies before states and applies membership/revision changes only
through the requested H1 cutoff. Earlier decisions retain the former zone,
identity and energy; later decisions contain exactly the engine's visible zones.
Completed runs count total_removal_count and total_revision_count; validation
checks these totals and full reconstructed states. Report `zones` denotes the
final visible zone count, not all historically observed zone incarnations.

New writes use schema 3 in the existing dedicated event collections, with the
same schema/run-scoped indexes. Existing schema-2 runs remain untouched. Read
them explicitly with `MongoEventReader(repo, run_id, schema_version=2)` or
`validate_event_run.py --schema-version 2`. Fresh schema-3 January smoke is
required before a new long replay; a schema-2 run cannot pass that gate.

## Approved zero-distance policy

`zero_distance_policy.py` implements a V2-only ReplayEngine subclass. When a
confirmed opposite reaction's extreme is exactly equal to the current OPEN
interaction's start price, and its temporal ordering is valid, reject that
reaction with reason `zero_distance`. Preserve the OPEN interaction, do not
finalize/score it, do not change the target's role or activate its interaction,
and continue processing the same candle's other V1 rules. This does not skip
candles or suppress other errors. A newly created zone's identity can remain
known even when its candidate interaction is rejected. Physical breaks remain
governed by V1. Nonzero prices use the original V1 activation method.

Rejections are retained in engine rejected_reactions and recorded append-only
in the event collection as kind `reaction_rejected`, with policy version,
origin/target/interaction IDs, equal endpoints, indexes and observed timestamp.
Readers replay these as audit records without changing zone state. Validation
checks their invariants and completed-run `total_rejection_count`. New runs
declare `reaction_policy=reject-zero-distance-v1`. Use the updated reader and
validator for runs containing rejection events and membership revisions.

This approved policy changes the source-code fingerprint. The earlier January
smoke must therefore be replaced by a **fresh successful smoke run** before any
long replay. Existing runs and V1/market data are left untouched. Event replay
prints processed H1 progress every 1,000 decisions; these lines are not commit
markers. `--progress-every` changes that interval.

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
list. Unchanged zones generate no events. The current state includes all zones
currently visible in the engine, including broken ones. Missing or revised
zones generate membership/revision events; their earlier observations remain
in immutable history. Future creation indexes, malformed states, NaN/Infinity,
unordered closes and sub-millisecond timestamps are rejected.

Each H1 checkpoint contains the complete causal decision, all zone boundaries,
zone ordering and exact numeric values. Compression is lossless. Its event_seq
is captured before future candles are fed. Missing H1 candles do not generate
invented snapshots. Higher-timeframe events after the final H1 decision may be
retained, but are excluded from that decision's cutoff.

`MongoEventReader(repo, run_id).reconstruct(aware_utc_h1_time)` reads the exact
compressed checkpoint. `from_events=True` independently replays zone creation
and changes through that decision's event cutoff; zone ordering and timeframe summary metadata
comes from the checkpoint. An instant without an H1 decision is rejected.
Readers accept only completed runs in the selected schema. Reading and validation perform no
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
# Zero-width boundary policy (V2)

The approved `reject-zero-width-boundary-v1` policy rejects a new zone candidate
when the selected boundary has identical finite lower and upper prices. The
oldest matching M15 candle is still selected using the original V1 rule; V2 does
not search for an alternative candle, widen prices, change market data, or
consume a zone/interaction ID. All remaining candle processing still runs.
Other validation errors propagate.

Successful staged rejections are retained in the engine's rejection history.
The observer records an immutable `boundary_rejected` event at the time the
rejection becomes known, with `zone_id: null` because no zone was created.
The audit includes the equal prices, reaction/detection indexes, C2 origin time,
and rejection time. Historical rejections introduced by origin-invalidation
replay are reported at the current observation; existing audits are not repeated.
Failed engine commits do not leak audits. Event readers validate the audit and
leave zone state unchanged. Run metadata includes `boundary_policy` and
`total_boundary_rejection_count`; validation reports
`zero_width_boundary_rejections`. This is an additive schema-3 event extension;
old records are not rewritten. The source fingerprint requires a fresh January
smoke before a long replay with this policy.
