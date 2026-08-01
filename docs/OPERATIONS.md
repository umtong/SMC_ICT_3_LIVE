# Operations and release runbook

## 1. Plan

Create a candidate manifest from an explicit historical interval and knowledge
date. Keep `as_of` in release metadata; it explains why the most recent month is
represented by daily rather than monthly objects.

## 2. Acquire Bronze

Download the companion `.CHECKSUM` first, then the ZIP. An existing file is
trusted only after a fresh local SHA-256 comparison. A missing object is
recorded as `source_unavailable`; it is not an exceptional listing-date guess.
A checksum mismatch is quarantined.

## 3. Normalize Silver

The normalizer validates source shape, time units, interval alignment, OHLC,
activity fields, monotonic order, duplicates and gaps. It then emits a
deterministic CSV.gz interchange file and JSON quality report.

## 4. Derive Gold

Derive larger timeframes only from a pinned 1m Silver release. Drop and count
incomplete buckets. Session/calendar views are derived, not embedded in Silver.

## 5. Catalog and publish

Hash every release file and write a catalog. Publish under an immutable version,
for example:

```text
05_RELEASES/market-data/v1.0.0/golden-2024-01/
05_RELEASES/market-data/v1.1.0/full-history-2026-07/
```

A release contains source manifest, download report, quality reports, catalog,
release metadata and data files or a content-addressed reference to them.

## 6. Detect upstream revisions

Binance may replace archived objects. A scheduled audit re-fetches checksum
files and compares them with the pinned release. A changed source never mutates
an old release. Instead:

1. record old and new provider checksums;
2. acquire the replacement into a new Bronze release;
3. rerun normalization and quality comparison;
4. explain row-level impact;
5. publish a new data version.

## Incremental cadence

- Daily: acquire the latest complete UTC day, validate and append a provisional
  daily release.
- Monthly: after the first Monday, acquire the official monthly object and
  reconcile it with provisional daily objects.
- Quarterly: revalidate historical checksums and instrument metadata.

## Recovery

Never edit an immutable release in place. Failed objects remain in Quarantine
with error and expected/actual hashes. A rerun is idempotent: verified objects
are reused; only absent or invalid objects are retried.
