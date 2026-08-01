# Backtest semantics and look-ahead boundaries

## Completed bars

A strategy using a 1-minute bar opened at `10:00:00 UTC` may use its full OHLC
and activity only at `10:01:00 UTC`. The canonical field for that boundary is
`available_time_us`, not the source close timestamp.

## Multi-timeframe construction

Higher timeframes are derived from the 1m base using UTC epoch-aligned buckets:

- open: first source open;
- high: maximum source high;
- low: minimum source low;
- close: last source close;
- volume/activity: sums only where the source defines those meanings;
- availability: exclusive end of the target bucket.

A target bucket is emitted only when every expected 1m open time exists. This
means a 15m feature cannot silently use 14 observed bars plus one fabricated
bar.

## Orders and fills

Market data does not define execution. Backtests must separately version:

- decision timestamp;
- order submission and activation latency;
- order type and time-in-force;
- spread, queue and partial-fill model;
- fee tier, funding and liquidation rules;
- price source used for trigger, fill and accounting;
- same-bar ambiguity policy.

A signal calculated at a bar close cannot fill at that bar's earlier close
price unless the execution model proves that timestamp and liquidity were
available.

## Sessions and daylight saving

Raw data stays UTC. Research views may derive Asia, London and New York session
features using an IANA timezone database. Hard-coded UTC offsets for New York
are forbidden because daylight-saving transitions would move the session.

## Missing data

A gap is not automatically an exchange halt, zero-volume bar or network fault.
It is an observed absence in a named source release. Analyses may exclude,
quarantine or model it, but must not rewrite it into an ordinary candle.

## Cross-source comparisons

Spot, futures trade price, mark price, index price and premium index are distinct
observables. A backtest must name the source used for signals, stops,
liquidations and P&L. They are never joined by timestamp and treated as one
interchangeable price.
