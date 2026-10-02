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
