# Data in Git

This directory contains both reproducibility metadata and the validated default
research release.

- `prepared/CURRENT`: selected default release ID
- `prepared/<release-id>/silver`: normalized 1-minute research data
- `prepared/<release-id>/gold`: deterministic 5m, 15m, 1h and 4h data
- `prepared/<release-id>/quality`: source and resampling quality evidence
- `prepared/<release-id>/catalog.csv`: file size, SHA-256 and row-range catalog
- `manifests/golden_2024_01.csv`: deterministic provenance/audit seed
- `manifests/full_history_candidates_2026-08-02.sha256`: contract for the separately generated full candidate manifest

Researchers use `prepared`; they do not need to download market data or locate a
Drive folder. Run the following from the repository root:

```bash
PYTHONPATH=src python3 -m smc_ict_data.cli ready --verify
```

Local acquisition workspaces such as `data/raw`, `data/silver`, `data/gold` and
`data/quality` remain ignored. A candidate manifest row is not a claim that an
upstream object exists; availability is established only while a maintainer
constructs or audits a release.
