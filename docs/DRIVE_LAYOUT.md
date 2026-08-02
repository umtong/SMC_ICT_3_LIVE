# Google Drive storage contract

## Boundary

The canonical project folder is:

```text
Project/SMC_ICT_3_LIVE
```

Google Drive is **durable artifact storage only**. It is not an execution
environment, scheduler, source checkout, Python environment, database runtime,
or researcher workspace.

Code runs from a GitHub checkout on a developer/research machine, an isolated
compute environment, or a GitHub Actions runner. Every command receives
explicit local input and output paths. No collector, normalizer, test, backtest,
or release job requires a mounted Google Drive path.

The repository and release tooling make no assumptions about any sibling or
parent Drive folders. They must not read from or write to anything outside
`Project/SMC_ICT_3_LIVE`.

## Layout

All paths below are relative to `Project/SMC_ICT_3_LIVE`.

| Folder | Contract |
|---|---|
| `00_README` | layout, release index and onboarding |
| `01_RAW_BRONZE` | exact provider bytes and checksums; append-only |
| `02_NORMALIZED_SILVER` | validated 1m records; no strategy labels |
| `03_DERIVED_GOLD` | deterministic higher timeframes and query artifacts |
| `04_CATALOG_QUALITY` | source/download manifests, hashes, gaps and QA |
| `05_RELEASES` | immutable, named bundles for experiments |
| `90_QUARANTINE` | failed/checksum-conflicting/semantic-conflicting objects |
| `99_ARCHIVE` | superseded but retained releases |

## Publication contract

Data is acquired, transformed, tested and cataloged on an execution surface
outside Drive. Only after validation succeeds are immutable artifacts uploaded
to the project folder.

Researchers download or materialize a pinned release into their own local
execution workspace. Experiments never mutate shared Drive evidence. A research
run identifies its inputs by release ID and SHA-256, not by an assumed Drive
mount path or by searching for a similarly named file.
