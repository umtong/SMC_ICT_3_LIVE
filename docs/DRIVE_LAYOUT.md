# Google Drive layout

The project Drive is the durable bulk-data surface. Folder numbers make the
lifecycle explicit and keep future researchers from inventing personal layouts.

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

Researchers receive read access to releases and may create workspaces outside
these managed folders. Production folders are written only by the release
pipeline so individual experiments cannot mutate shared evidence.
