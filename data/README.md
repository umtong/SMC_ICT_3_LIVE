# Data in Git

Only small manifests and documentation belong here. Bulk ZIP, CSV.gz, Parquet,
DuckDB and quality trees are ignored by Git and published to the project Google
Drive as immutable releases.

- `manifests/golden_2024_01.csv`: deterministic CI and release seed
- `manifests/full_history_candidates_2026-08-02.sha256`: hash and row-count contract for the full candidate CSV distributed in Drive. Regenerate it with the README command.

A candidate row is not a claim that the object exists. `download_report.jsonl`
is the authoritative source-availability result for a release.
