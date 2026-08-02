# Data architecture

## Design decision

The system uses an event-sourcing / medallion hybrid:

```text
Official source objects
        ↓ checksum + immutable identity
Bronze: exact ZIP and CHECKSUM
        ↓ schema-aware normalization
Silver: UTC microsecond 1m logical records
        ↓ deterministic transformation only
Gold: complete higher timeframes and research views
        ↓ version-pinned feature/scenario code
Backtest and live-common decision interfaces
```

This borrows controls from adjacent fields rather than treating OHLCV as an
ordinary spreadsheet:

- **Event sourcing:** Bronze is append-only evidence. Corrections create a new
  release and lineage edge rather than overwriting history invisibly.
- **Bitemporal databases:** `open_time_us` describes market event time;
  `available_time_us` describes when a complete bar may legally be consumed;
  release metadata describes when this project learned a source version.
- **Software supply-chain security:** every external object is paired with a
  provider checksum and an internally calculated SHA-256; releases resemble an
  SBOM for data.
- **Dead-letter queues:** checksum mismatches and semantic conflicts go to
  Quarantine and never leak into research queries.
- **Slowly changing dimensions:** future instrument metadata (tick size,
  contract size, status, fee tier) must be effective-dated, not overwritten.
- **Data contracts:** schemas and CI tests are versioned with code and golden
  manifests.

## Storage responsibilities

### GitHub

Small, reviewable and executable artifacts only:

- collectors and normalizers;
- configuration and schemas;
- source/candidate manifests;
- quality-contract tests;
- SQL views and documentation;
- workflow definitions and release metadata templates.

### Google Drive

Bulk and release artifacts:

- exact raw archives and companion checksums;
- normalized Silver partitions;
- derived Gold partitions;
- quality reports and catalogs;
- immutable release bundles.

## Partition contract

The physical hierarchy follows source semantics:

```text
{exchange}/{market_path}/{dataset}/{symbol}/{interval}/{year}/{month}/{file}
```

Examples:

```text
binance/spot/klines/BTCUSDT/1m/2024/01/BTCUSDT-1m-2024-01.zip
binance/futures/um/markPriceKlines/ETHUSDT/1m/2024/01/ETHUSDT-1m-2024-01.csv.gz
```

Monthly partitions avoid tiny-file proliferation while still permitting
bounded replay. Daily source objects are used for the not-yet-published month;
a later release may compact them only after the official monthly object is
published and reconciled.

## Neutrality boundary

Silver contains observable source facts and explicit temporal semantics. It
must not contain an SMC/ICT label, inferred structure state, trading signal,
position, stop, take-profit or outcome. Those belong to versioned feature and
scenario packages that consume a pinned data release.
