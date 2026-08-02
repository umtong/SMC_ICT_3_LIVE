# Normalized kline data contract

## Logical key

```text
(exchange, market_path, dataset, symbol, interval, open_time_us)
```

A duplicate with the same key and identical source fields is removed with an
audit count. A duplicate with different fields is a hard contract violation.

## Temporal fields

| Field | Meaning |
|---|---|
| `open_time_us` | inclusive UTC interval start |
| `close_time_exclusive_us` | exclusive UTC interval end, computed from interval |
| `available_time_us` | earliest legal time for a completed-bar strategy to consume the record |
| `source_close_time_us` | source-provided inclusive/near-inclusive close timestamp, preserved for audit |

The canonical interval is `[open_time_us, close_time_exclusive_us)`. The source
close timestamp may be one microsecond or one millisecond before the exclusive
end depending on source and era. It is never used to decide signal availability.

## Price and activity fields

OHLC is preserved as decimal text in the dependency-free CSV.gz interchange
format. This prevents premature binary-float rounding. Consumers may cast to a
suitable fixed decimal type.

`base_volume`, `quote_volume`, `trade_count` and taker-buy fields have semantics
only for trade-price `klines`. They are empty for mark, index and premium
reference-price klines. Original positions 5 and 7–11 remain in
`source_field_*` so no source information is discarded or mislabeled.

## Required invariants

- timestamps normalize to UTC integer microseconds;
- open times are aligned to the declared fixed interval;
- source rows are monotonically increasing;
- `high >= max(open, low, close)`;
- `low <= min(open, high, close)`;
- prices and trade activity are finite and nonnegative;
- close time is consistent with the interval;
- source archive SHA-256 equals the provider checksum;
- gaps are reported and never forward/back-filled;
- incomplete derived buckets are dropped and counted.

## File determinism

CSV.gz output uses UTF-8, LF endings, a fixed column order and gzip `mtime=0`.
Given the same source bytes, manifest row and pipeline version, normalized bytes
are reproducible.

## Schema evolution

Breaking semantic changes require a major pipeline/data-contract version and a
new release path. Adding nullable audit fields requires a minor version. A
consumer must pin both data release and schema version.
