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
- **Data contracts:** schemas and CI tests are versioned with code and prepared
  release catalogs.

## Default research surface

A validated, bounded Silver/Gold release is committed under `data/prepared`.
It is the default input for all researchers and is available immediately after
cloning `main`. No Drive mount, exchange API call, archive download or data-vendor
selection is part of the normal research bootstrap.

`data/prepared/CURRENT` selects one immutable release. The release contains a
machine-readable metadata contract and a SHA-256 catalog. CI verifies the
catalog and every tracked data file.

## Storage responsibilities

### GitHub

The repository is the single research entrypoint and contains:

- collectors, normalizers and deterministic resamplers;
- configuration, schemas, tests and workflows;
- source/candidate manifests and release metadata;
- a versioned research-ready Silver/Gold release;
- its quality reports and content catalog;
- SQL views and documentation.

The committed release is deliberately bounded so cloning remains practical.
Additional periods are published as explicit, reviewed data-version changes;
they are not silently fetched during a strategy run.

### Google Drive

Drive is optional durable archive and backup storage for:

- exact raw archives and companion checksums;
- historical release bundles;
- superseded or larger data artifacts.

Drive is not an execution environment and is not required to locate, initialize
or run the default research dataset. Code must not assume any Drive folder
outside `Project/SMC_ICT_3_LIVE`.

## Partition contract

The physical hierarchy follows source semantics:

```text
{exchange}/{market_path}/{dataset}/{symbol}/{interval}/{year}/{month}/{file}
```

Examples:

```text
data/prepared/<release>/silver/binance/spot/klines/BTCUSDT/1m/2024/01/BTCUSDT-1m-2024-01.csv.gz
data/prepared/<release>/gold/binance/futures/um/markPriceKlines/ETHUSDT/15m/2024/01/ETHUSDT-15m-2024-01.csv.gz
```

Monthly partitions avoid tiny-file proliferation while still permitting
bounded replay. Daily source objects may be used while constructing a future
release, but researchers consume only the reviewed release output.

## Acquisition boundary

Official downloads and Bronze materialization remain available for maintainers
who create a new release or audit provenance. They do not run on every pull
request and are not a prerequisite for strategy work. The default CI path reads
and verifies the committed prepared release without external market-data I/O.

## Neutrality boundary

Silver contains observable source facts and explicit temporal semantics. It
must not contain an SMC/ICT label, inferred structure state, trading signal,
position, stop, take-profit or outcome. Those belong to versioned feature and
scenario packages that consume a pinned data release.
