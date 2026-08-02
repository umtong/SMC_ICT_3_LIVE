# Google Drive storage contract

## Boundary

The canonical project folder is:

```text
Project/SMC_ICT_3_LIVE
```

Google Drive is **optional durable archive and backup storage only**. It is not
an execution environment, scheduler, source checkout, Python environment,
database runtime, researcher workspace or prerequisite for using the default
market data.

The research-ready release is committed in Git under `data/prepared`. Code runs
from a GitHub checkout on a developer/research machine, an isolated compute
environment, or a GitHub Actions runner. No collector, normalizer, test,
backtest or release job requires a mounted Google Drive path.

The repository and release tooling make no assumptions about any sibling or
parent Drive folders. They must not read from or write to anything outside
`Project/SMC_ICT_3_LIVE`.

## Optional archive layout

All paths below are relative to `Project/SMC_ICT_3_LIVE`.

| Folder | Contract |
|---|---|
| `00_README` | layout, release index and onboarding |
| `01_RAW_BRONZE` | exact provider bytes and checksums; append-only |
| `02_NORMALIZED_SILVER` | archived validated 1m records |
| `03_DERIVED_GOLD` | archived deterministic higher timeframes |
| `04_CATALOG_QUALITY` | source/download manifests, hashes, gaps and QA |
| `05_RELEASES` | immutable backup bundles |
| `90_QUARANTINE` | failed/checksum-conflicting/semantic-conflicting objects |
| `99_ARCHIVE` | superseded but retained releases |

## Publication contract

Data is acquired, transformed, tested and cataloged on an execution surface
outside Drive. A bounded default release is committed to Git and selected by
`data/prepared/CURRENT`; this is what researchers use.

After validation, the same release may also be uploaded to the project Drive
for long-term retention. Experiments never mutate either the committed release
or shared archive evidence. A research run identifies its inputs by Git commit,
release ID and catalog SHA-256, not by a Drive mount path or filename search.
