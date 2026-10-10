# Zone Energy — multi-timeframe historical replay (prototype)

Scope: XAUUSD only; closed H1, H4 and D1 candles; chronological replay for 2010–2026.

## Time and causality contract
- `ClosedBar.closed_at` is a timezone-aware instant at which the completed bar is available, **not its opening time**. Normalize source/broker candle sessions and timestamps before using this module.
- H1 is the decision clock. The engine receives a candle only at its close time. H4/D1 updates with equal timestamps are applied before that H1 decision.
- The three timeframes may have no historical bar yet; in that case `snapshot()` is still called and should return empty zones.
- `ZoneEngineAdapter.on_closed_bar()` is responsible for applying the existing Zone Energy formation, scoring, interaction and role-change rules in a strictly causal manner. `snapshot()` returns the current known zones. The replay module intentionally does **not** implement or alter zone rules.
- Snapshot results are deep-copied, preventing future mutation from silently changing previously recorded decisions.
- For valid research labels, attach future price outcomes **only after** persisting the decision-time feature snapshot; never use the label to compute the snapshot.
- OHLC input and time alignment are prerequisites; there is no live market feed or model training in this prototype.

## Running tests

```bash
cd V2_MultiTimeframe
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Next step
Plug in the project's existing zone engine through `ZoneEngineAdapter`. Add tests comparing historical prefix replay against full replay for each timestamp, then build the feature/label dataset.
