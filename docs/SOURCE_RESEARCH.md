# Source research and selection record

Reviewed: 2026-08-02 UTC

## Canonical source

**Binance Public Data / Binance Vision** is the canonical bulk source because it
provides daily and monthly archives, companion SHA-256 checksums, documented
Spot and Futures kline layouts and official helpers for trade, mark, index and
premium price archives.

The source states that daily data becomes available the next day and monthly
data on the first Monday of the month. It also warns that Spot timestamps from
2025-01-01 onward use microseconds and that archived files may later be revised.
Those facts directly determine our planner, timestamp decoder and release
revision policy.

Official references:

- https://github.com/binance/binance-public-data
- https://data.binance.vision/
- https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
- https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api

## REST APIs

REST endpoints are suitable for live tails, narrow reconciliation and exchange
metadata. They are not the first choice for full bulk history because pagination
and rate limits add unnecessary state. REST-recovered rows must be stored as a
separate source lineage; they do not silently patch official archive gaps.

## Evaluated mirrors and accelerators

### `linxy/USDT-M_Perpetual_Futures`

Per-symbol Parquet with 5m and higher trade/mark/index/premium klines, metrics,
funding and metadata. It is useful for quick exploratory work and independent
content comparison, but does not replace canonical 1m official archives.

### `linxy/CryptoCoin`

Per-symbol Binance Spot Parquet at 5m and higher, updated daily. It is a useful
bootstrap/cache candidate, again requiring reconciliation and explicit mirror
lineage.

### Community 1s/tick/L2 datasets

They can support execution and microstructure studies, but storage volume,
venue coverage, reconstruction rules and licensing differ materially. They are
an optional research track, not a transparent upgrade to a 1m bar release.

## Sources deliberately not spliced together

Coinbase, Kraken, OKX and other venues are valuable for outage checks,
cross-venue price discovery and robustness tests. Their bars must remain
venue-specific. Filling a Binance gap with another exchange creates a price
series that never traded on either venue and invalidates venue-specific fees,
liquidity and execution assumptions.

## Additional context tracks

The architecture leaves separate, joinable namespaces for:

- effective-dated instrument filters and contract specifications;
- fee schedules and funding history;
- open interest and positioning metrics;
- exchange incident/outage annotations;
- economic calendar and session/DST features;
- on-chain or stablecoin-regime context.

None of these mutates the canonical price record. Each receives its own source,
availability timestamp and revision policy.
