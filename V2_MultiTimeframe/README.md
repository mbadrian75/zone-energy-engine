# Zone Energy V2 — XAUUSD multi-timeframe integration

The V2 folder does not modify V1. It instantiates one unmodified V1 `ReplayEngine` per timeframe (H1, H4, D1), then produces one combined decision snapshot at every H1 close.

## Architecture

1. `market_streams.py` converts start-stamped V1/Mongo candles into completed bars (UTC assumed). No incomplete bar is supplied to the zone engine.
2. `multi_timeframe_replay.py` interleaves H1/H4/D1 based on candle close time. D1 and H4 closes at the same instant are processed before the H1 decision.
3. `v1_adapter.py` runs three independent V1 engines. It reuses V1 zone creation, role changes, breaks, interactions, energy calculation and M15 boundary rules without reimplementing them. Zone IDs are namespaced, e.g. `H1:2` versus `H4:2`.
4. `run_v1_multitimeframe.py` reads XAUUSD from V1 MongoDB, producing JSON Lines with one combined snapshot per H1 close.

## Historical-data contract and caveats

- The repository's HistData ingestion stores naive candle **opening** timestamps and constructs H1/H4/D1 buckets anchored to midnight. This implementation treats those as UTC wall-time. Confirm actual source timezone, DST treatment, broker session and daily close boundary before trusting historical conclusions. Vendor-local time requires explicit normalization.
- V1 still uses M15 candles from each C2 window to locate zone boundaries. M15 coverage must be checked separately; missing M15 means missing zones.
- Provide fixed, precommitted annual candle-count calibration for H1/H4/D1. Do not derive constants using *future* historical observations of the prediction window.
- H4 and D1 are updated only when their candles close. An unchanged higher-timeframe snapshot stays at its latest completed-candle index.
- Replay starts from empty engine state. A 2025-only replay does not have the zone history that would exist after continuous replay from 2010. Use enough historical warm-up for model features.
- Undefined V1 effective energy is retained as `None`, not incorrectly converted to zero. ACTIVE and BROKEN zones are both included with their current known states.
- These outputs are causal **features**, not response labels, predictions or executable trading orders.

## Run with MongoDB

From repository root, with existing V1 dependencies and MongoDB available:

```bash
python V2_MultiTimeframe/run_v1_multitimeframe.py \
  --start 2025-01-01 --end 2025-02-01 \
  --year-candles-h1 6000 --year-candles-h4 1500 --year-candles-d1 250 \
  --output v2-decisions-2025-01.jsonl
```

**The three candle counts above are illustrative placeholders only**, not verified historical counts or approved calibrations. The Mongo candle collections are read-only. The output is opened in exclusive mode and will not overwrite previous results.

## Tests

```bash
cd V2_MultiTimeframe
python -m unittest discover -s tests -v
```

The core replay tests need only V2; the V1 integration tests require a complete repository checkout. Also run the unchanged V1 regression suite:

```bash
python -B V1/scripts/run_engine_tests.py
```

## Next

Perform a historical 2025 smoke test after the timestamp convention, M15 data coverage and annual-decay calibration have been verified. Compare each timeframe against a matching V1 single-timeframe replay, then conduct causal 2010–2026 data extraction and label building.
