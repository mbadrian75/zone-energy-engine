# Zone Energy Engine V1

Implementation of the Zone Energy V1 specification and state machine.

## Components

- Historical Market Data
- Replay Engine
- Zone State Machine
- Movement Energy
- Zone Energy
- Testing and Calibration

## Data Source

MongoDB database: market_data

Symbol: XAUUSD

Timeframes:
- D1
- H4
- H1
- M30
- M15
- M5
- M1

## Run engine tests

From the repository root:

```powershell
python -B V1/scripts/run_engine_tests.py
```

The runner discovers `V1/scripts/test_*.py`, runs each script in a separate
Python process, and exits with a nonzero status if any test script fails or
exceeds its 30-second timeout. Assertions remain enabled. Add `--verbose`
to see output from successful tests.

The default run uses local tests, including boundary-service tests with an
in-memory repository. The live MongoDB repository and boundary-service tests
are skipped; to include them when the database is available:

```powershell
python -B V1/scripts/run_engine_tests.py --include-database
```

These tests verify engine components and synthetic lifecycle scenarios.
Historical market replay and strategy calibration require separate validation.

## Replay real candles and save results

```powershell
python -B V1/scripts/run_replay.py --timeframe H1 --start 2025-01-01 --end 2025-02-01 --reference-year 2025 --checkpoint-every 100
```

Use `--reference-year` only for a year whose candle history is fully populated;
the command reports the actual candle count used for decay. Alternatively pass
an explicitly calibrated `--year-candles` count. Dates follow the timestamp
convention of the stored candles; `--end` is exclusive. M15 data must also exist
for each main-timeframe C2 window.

The replay keeps one OPEN interaction. An opposite confirmed reaction closes
the current move at its new extreme and starts the next interaction. Same-role
reversals do not start concurrent moves. Role changes use the external price
side saved before the current candle. Reactions are confirmed before current
candle breaks; all breaks in that batch share a pre-break snapshot.

ACTIVE-zone returns precede role changes; within either group, the latest
creation index wins. Tied candidates abort the candle without partial state.
Dual high/low patterns select the opposite of the current reaction type; without
a previous reaction they remain unresolved.

If the current origin zone breaks before a confirmed opposite reaction, only
its latest reaction is invalidated. Replay restores the preceding origin and
reconstructs candles from before the invalid reaction, including intervening
break snapshots. The zone remains present and becomes BROKEN, with its earlier
valid interaction energies preserved. The discarded reaction is retained in
`replay_context.invalidated_reactions`, outside valid energy sums. If there is
no preceding origin, the break remains unattributed. Older checkpoint documents
are unchanged; corrections appear in subsequent checkpoints. This processing
keeps in-memory reaction seeds and is currently available for fresh replays,
not for checkpoint resume. Run a fresh replay after changing these rules.

Physical breaks lacking an eligible
confirmed origin are retained under `replay_context.unattributed_breaks`; no
origin energy is fabricated. Missing M15 boundaries skip creation of that zone.

Periodic checkpoints and the final state are written to
`market_data.zone_energy_checkpoints`. Each run gets a unique ID unless
`--run-id` is supplied. Set `ZONE_ENERGY_MONGO_URI` for a different connection,
and `--database` for a different database. Candle collections remain read-only.
This initial replay starts from the beginning of the supplied range; loading a
checkpoint into models is supported, but resuming mid-run is not yet implemented.

## Save engine results in the candle database

Bootstrap policy: undefined energy remains `None` in historical records.
Interaction/zone sums and the active-zone median use defined contributions
only. A zone with only undefined closed energy remains undefined. A break
with an unknown zone energy or a missing/zero median is still recorded and
changes the zone to BROKEN; barrier ratio, cost and break evidence remain
`None` until a usable reference exists. Historical snapshots are not rescored.

`EngineResultsRepository` defaults to `mongodb://localhost:27017/` and the
existing `market_data` database. It writes only to `zone_energy_checkpoints`;
the `xauusd_*` candle collections are not used for writes.

A checkpoint contains the complete zone/interaction history, immutable break
snapshots, effective zone energies at the saved candle, timeframe, configuration,
and yearly candle count. Saving the same checkpoint again is idempotent;
different data under the same identity is rejected rather than replacing history.
Use a distinct `run_id` for each replay or live sequence, with consistent candle
indexing inside a run. Each checkpoint must fit MongoDB's single-document size limit.

Example from a program with an already calculated zone history:

```python
from zone_energy.config import EngineConfig
from zone_energy.data import EngineResultsRepository

repository = EngineResultsRepository()
try:
    checkpoint_id = repository.save_checkpoint(
        zones,
        run_id="xauusd-h1-replay-001",
        symbol="XAUUSD",
        current_candle_index=current_index,
        year_candles=year_candles,
        config=EngineConfig(),
    )
    restored_zones = repository.load_zones(checkpoint_id)
finally:
    repository.close()
```

The caller invokes saving after a successful engine transition; this repository
does not run a market replay or automatically save on every candle.
The MongoDB test enabled by `--include-database` also checks checkpoint writes,
reads, and duplicate-save behavior. It creates a unique test run in the results
collection and removes only its own test record afterward.
