# Validation record — 2026-10-11

Latest storage model: schema 3 records observed zone removal and identity
revision instead of rejecting changes caused by V1 origin-invalidation replay.
Local suite: 48 tests discovered, 45 passed, 3 live tests skipped. Earlier H1
states, removed/reappearing local IDs, full before/after revisions, corrupted
prior-state rejection and schema-2 read compatibility are covered. All 504
January decisions and 116 zones still match JSONL and event reconstruction.
No V1 or market-data file changed. A fresh schema-3 server smoke is required.

The user supplied a successful policy-enabled schema-2 server smoke:
all 45 tests passed, run `v2-events-jan2025-e5342cec820e4db298140b40f630f306`,
504 decisions, 19,868 events, 116 zones, both equivalence flags true. The next
long run `v2-events-2010-2026-c9603a7a02fe4af48001f298fdb74d1f` then passed
8,000 H1 decisions before the writer's incorrect “Known zones cannot disappear”
assumption stopped it. It remains an incomplete run; no resume or deletion is
performed. Schema 3 keeps all old records and scopes new writes to version 3.

After the user approved rejecting zero-distance reactions, V2 now implements
that policy without modifying V1 files. Local validation: 45 tests discovered,
43 passed, 2 opt-in live MongoDB tests skipped. The supplied H1/2011-02-10
scenario (interaction 1800, origin 424, role-change target 386, equal endpoints
1360.43, four-candle duration) is reproduced with a minimal seeded engine state.
Unmodified V1 raises; V2 rejects the reaction, keeps the OPEN interaction and
target role, advances the candle and continues. Nonzero seeded activation equals
V1 exactly; immediate/delayed/new-zone reactions, temporal errors and immutable
Mongo rejection audit reconstruction are covered. January's 504 JSONL decisions
and 116 zones still match in offline equivalence. Fresh actual server smoke is
required because production source-code fingerprint changed. This is not a
claim that the full sixteen-year replay completed.

Committed-history comparisons also capture older zero-distance rejections
introduced by V1 invalidation replay at the current observation timestamp,
without repeating unchanged rejection history. A failed engine before_commit
does not leak the staged rejection. The V2 updater downloads all required files
from a pinned commit before copying any, then runs a fresh January smoke; it
does not start a long replay or remove database data.

Server output subsequently supplied by the user reports all 35 tests passed,
including the real MongoDB contract, followed by the actual January replay:
run `v2-events-jan2025-4283f0662f1e462796ff3a76585db22e`, 504 decisions,
19,868 events, 116 zones, both equivalence flags true. Compressed payload on
that server: 1,067,412 bytes. These figures are from the supplied server log.

The requested 2010–2026 replay then aborted inside unchanged V1
InteractionCloser with zero movement distance. January equivalence does not
establish validity of every V1 path on sixteen years of data. Added a read-only
diagnostic replay under diagnostics/ to capture the failing timeframe/candle,
actual closing endpoint and interaction without changing V1 or MongoDB data.
Its synthetic zero-distance extraction test passes. No skip or recovery policy
for the engine error is introduced.

Base repository commit: `bba0bd6` (origin/main at implementation start).

- Baseline V2 suite: 17 tests passed before changes.
- Updated V2 suite: 35 tests discovered; 34 passed, 1 live MongoDB test skipped.
- The second server attempt passed live persistence, reconstruction and duplicate
  checks, then exposed a test-only index metadata shape error. Index keys now
  accept PyMongo's list of pairs as well as mapping form, with regression coverage.
  The full server smoke must still be rerun through January replay/validation.
- Windows Server output exposed a MongoClient constructor option error before
  any database operation: `j=True` is not accepted. The client now uses
  `journal=True`; collection WriteConcern correctly retains `j=True`. A
  constructor regression test covers the option names. Server smoke must be rerun.
- Actual V1 engine integration: observer-enabled output matches the original
  replay output at every synthetic H1 decision.
- January checked-in JSONL equivalence: all 504 complete decisions and all 116
  zones match, including every boundary, state, type, count and energy value.
- Offline JSONL-derived events: 19,835. These are not claimed to be the count
  from a live replay of all underlying higher-timeframe candles.
- Checkpoint JSON payload: 6,795,914 bytes before compression;
  1,089,953 bytes after compression (about 84% reduction). This measures payload,
  not BSON/index/disk overhead or total event-storage cost.
- Fault injection: partial event insert, partial checkpoint insert, failed
  progress marker, duplicate run, missing event, checksum corruption, malformed
  input, future exclusion and writer poisoning covered.
- Higher-timeframe gap observations and terminal events covered separately.
- Zone reordering and decreases in V1 interaction_count preserved.
- PowerShell smoke script parsed successfully with the PowerShell parser.
- `git diff --check` passed; no V1 or Data files changed.

No live MongoDB or real January market replay was executed in this local
validation. The Windows smoke script enables the live contract test, performs
the actual market replay and validates every decision against January JSONL.
It must pass on the server before a long replay is accepted. The event runner
also revalidates a matching January smoke run before intervals over 31 days.

Run the suite from the repository root with V2 and V1/src on PYTHONPATH:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONPATH = 'V2_MultiTimeframe;V1/src'
& .\.venv\Scripts\python.exe -m unittest discover -s V2_MultiTimeframe/tests -v
```

See [MONGODB_EVENTS.md](MONGODB_EVENTS.md) for the real server smoke procedure.
