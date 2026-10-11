# Validation record — 2026-10-11

Base repository commit: `bba0bd6` (origin/main at implementation start).

- Baseline V2 suite: 17 tests passed before changes.
- Updated V2 suite: 34 tests discovered; 33 passed, 1 live MongoDB test skipped.
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
