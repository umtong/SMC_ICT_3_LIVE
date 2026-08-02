# Researcher guide

## Start from the prepared release

The repository already contains the validated default market-data release.
Do not begin a strategy task by searching Google Drive, choosing another data
vendor, or downloading Binance archives again.

```bash
PYTHONPATH=src python3 -m smc_ict_data.cli ready --verify
```

`data/prepared/CURRENT` identifies the default release. Use the returned
`silver_root` for 1-minute source facts and `gold_root` for the committed 5m,
15m, 1h and 4h derivatives. Upstream acquisition commands are for data-release
maintainers and provenance audits, not the normal research path.

## Pin inputs

Every experiment records:

- Git commit of strategy/feature code;
- market-data release ID and catalog SHA-256;
- source dataset(s) and symbols;
- decision and execution timestamp policy;
- fee, funding, latency and slippage model;
- train/validation/test or walk-forward boundaries;
- scenario definition version and parameter set.

## Query the source you intend

Do not use an unqualified `close`. Name the dataset:

- Spot trade close;
- USD-M trade close;
- mark close;
- index close;
- premium index close.

The correct source depends on whether the study concerns signal formation,
order execution, liquidation, funding basis or accounting.

## Keep pattern detection separate from scenarios

A liquidity sweep, FVG or structure event is an observation produced by a
versioned detector. A trading scenario is a causal state machine that orders
market state, expected liquidity path, confirmation, entry, invalidation and
exit. Neither belongs in the neutral Silver data layer.

## Diagnose by scenario, not only aggregate return

Store event-level diagnostics that answer:

- which scenario generated the trade;
- what market and session state existed;
- which liquidity objective was expected and whether it was reached;
- whether direction or timing failed;
- which invalidation fired;
- which asset/regime/date contributed the result;
- whether performance survives a new data/source release.

## Prohibited shortcuts

- forward/back-filling missing candles as normal price action;
- using current instrument metadata for historical periods without effective
  dates;
- mixing mark/index/trade prices without a declared rule;
- entering at a price observed before `available_time_us`;
- selecting only periods after each asset became successful and calling it a
  universal portfolio test;
- tuning on the final holdout or changing data cleaning after viewing outcomes.
