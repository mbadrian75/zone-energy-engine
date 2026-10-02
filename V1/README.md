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
