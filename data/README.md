# Data surfaces

## `prepared/`

The bounded golden release is committed in Git for immediate, network-free
contract, CI and scenario work.

- `prepared/CURRENT`: bundled release ID
- `prepared/<release-id>/silver`: normalized 1-minute data
- `prepared/<release-id>/gold`: deterministic 5m, 15m, 1h and 4h data
- `prepared/<release-id>/quality`: source and resampling evidence
- `prepared/<release-id>/catalog.csv`: size, SHA-256 and row-range catalog

## `distributions/`

Small descriptors for full-history GitHub Release distributions. The remote
index named by the descriptor contains final annual asset sizes, SHA-256 values,
file counts and row counts.

## `installed/`

Created locally by `smc-data install` and intentionally ignored by Git. It holds
the complete verified history assembled from project-produced annual GitHub
Release assets. When `installed/CURRENT` exists, the default loader selects it
before the bundled golden release.

```bash
smc-data install
smc-data ready --verify
```

Neither installation nor research requires Google Drive or an exchange data
download.

## `manifests/`

- `golden_2024_01.csv`: deterministic provenance/audit seed
- `full_history_candidates_2026-08-02.sha256`: contract for the complete candidate manifest used by release maintainers

Local acquisition workspaces such as `data/raw`, `data/silver`, `data/gold` and
`data/quality` remain ignored. Candidate manifest rows do not assert source
existence; release construction records unavailable objects explicitly.
