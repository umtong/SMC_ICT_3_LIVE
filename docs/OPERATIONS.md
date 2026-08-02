# Operations and release runbook

## Researcher path

Normal research does not execute this acquisition runbook. Researchers use the
release selected by `data/prepared/CURRENT` and verify it locally:

```bash
PYTHONPATH=src python3 -m smc_ict_data.cli ready --verify
```

That release is committed in Git with Silver, Gold, quality reports and a
content catalog. Drive and upstream exchange downloads are not runtime
dependencies.

The remaining sections are for maintainers creating or auditing a data release.

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

Hash every release file and write a catalog. A reviewed, bounded default release
is committed under:

```text
data/prepared/<release-id>/
```

Update `data/prepared/CURRENT` in the same pull request. CI must verify every
cataloged file before merge. Google Drive may receive an immutable backup bundle
under `Project/SMC_ICT_3_LIVE`, but that backup is not the researcher entrypoint.

A release contains source manifest, download report, quality reports, catalog,
release metadata and research-ready Silver/Gold files. Bronze may remain in the
archive when it is unnecessary for normal strategy work.

## 6. Detect upstream revisions

Binance may replace archived objects. A provenance audit re-fetches checksum
files and compares them with the pinned release. A changed source never mutates
an old release. Instead:

1. record old and new provider checksums;
2. acquire the replacement into a new Bronze release;
3. rerun normalization and quality comparison;
4. explain row-level impact;
5. publish a new data version through review.

The `audit-golden-source-reproducibility` workflow is explicit/manual and is not
run on every strategy pull request.

## Incremental cadence

- As needed: acquire the latest complete UTC period for a candidate release.
- Before publication: reconcile daily candidates with official monthly objects.
- At audit points: revalidate historical checksums and instrument metadata.

No cadence silently changes `data/prepared/CURRENT`. Publication always requires
an explicit release commit and review.

## Recovery

Never edit an immutable release in place. Failed objects remain in Quarantine
with error and expected/actual hashes. A rerun is idempotent: verified objects
are reused; only absent or invalid objects are retried.
