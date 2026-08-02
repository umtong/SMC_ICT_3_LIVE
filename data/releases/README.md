# Published data releases

This directory stores small, reviewable release indexes. Bulk data remains in
the project Google Drive and is addressed by immutable file IDs and SHA-256.

- `golden-2024-01-v1.0.0.json`: 4 symbols × 5 official 1m source datasets for
  January 2024, plus pre-materialized 5m/15m/1h/4h Gold files.

A release index is the authoritative bridge between Git code, source manifests,
Google Drive objects, row/gap/duplicate diagnostics and bundle hashes. Never
identify a dataset by a human-readable Drive filename alone; pin the release ID
and SHA-256 recorded here.
