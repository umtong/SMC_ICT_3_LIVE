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

## Research surfaces

### Bundled golden contract release

A bounded Silver/Gold release is committed under `data/prepared`. It is
available immediately after cloning `main` and is used for code, schema, CI and
scenario-contract work without network access.

`data/prepared/CURRENT` selects the immutable bundled release. CI verifies its
catalog and every tracked file.

### Full-history prepared distribution

The complete research period is too large for ordinary Git history. It is
therefore materialized once by the project and published as immutable yearly
assets under a versioned GitHub Release.

```text
GitHub Release index
        ↓ asset size + SHA-256
Yearly prepared ZIP
        ↓ internal catalog verification
Silver / Gold / quality files
        ↓ merged catalog + final verification
data/installed/<release-id>
```

`smc-data install` downloads project-produced assets, never exchange archives.
It validates the outer ZIP and every inner file, installs atomically, and writes
`data/installed/CURRENT`. The loader gives an installed full-history release
priority over the bundled golden release.

## Storage responsibilities

### GitHub repository

- collectors, normalizers and deterministic resamplers;
- configuration, schemas, tests and workflows;
- source/candidate manifests and release metadata;
- the bounded golden Silver/Gold release;
- loaders, installers, catalogs and documentation.

### GitHub Releases

- prebuilt yearly full-history Silver/Gold partitions;
- partition metadata and quality evidence;
- a distribution index containing asset URLs, sizes, SHA-256 values, row and
  file totals;
- permanent, versioned installation inputs for researchers.

### Google Drive

Drive is optional archive and backup storage for raw evidence or duplicate
release bundles. It is not an execution surface and is not required for clone,
installation or research. Code must not assume any Drive folder outside
`Project/SMC_ICT_3_LIVE`.

## Partition contract

The physical hierarchy follows source semantics:

```text
{exchange}/{market_path}/{dataset}/{symbol}/{interval}/{year}/{month}/{file}
```

Examples:

```text
data/prepared/<release>/silver/binance/spot/klines/BTCUSDT/1m/2024/01/BTCUSDT-1m-2024-01.csv.gz
data/installed/<release>/gold/binance/futures/um/markPriceKlines/ETHUSDT/15m/2024/01/ETHUSDT-15m-2024-01.csv.gz
```

Monthly files avoid tiny-file proliferation while annual distribution assets
permit independent retry, checksum verification and selective installation.
Daily source objects may be used while constructing a release, but researchers
consume only reviewed Silver/Gold output.

## Acquisition boundary

Official downloads and Bronze materialization are release-maintainer work. The
full-history builder performs them once, validates provider checksums, derives
Gold, packages yearly assets and publishes the GitHub distribution index.
Researchers never repeat this path.

Ordinary pull-request CI reads the bundled release and uses local fixtures. The
full-history build is triggered explicitly as a versioned publication workflow,
not on every strategy change.

## Neutrality boundary

Silver contains observable source facts and explicit temporal semantics. It
must not contain an SMC/ICT label, inferred structure state, trading signal,
position, stop, take-profit or outcome. Those belong to versioned feature and
scenario packages that consume a pinned data release.
