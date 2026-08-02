# Operations and release runbook

## Researcher path

Normal research does not execute the acquisition runbook.

```bash
make setup-full
smc-data ready --verify
```

This installs project-produced GitHub Release assets into `data/installed` and
verifies every file. It does not use Google Drive or download exchange archives.
The bundled `data/prepared` golden release remains available for immediate,
network-free contract work.

The remaining sections are for data-release maintainers.

## 1. Plan

Create candidate manifests from explicit historical intervals and a knowledge
date. Keep `as_of` in release metadata; it explains why a recent month may use
daily rather than monthly source objects.

The v1 full-history distribution is partitioned by UTC calendar year from
2017-01-01 through 2026-07-31. A candidate URL does not assert that a symbol or
dataset existed; source 404s are recorded as `source_unavailable`.

## 2. Acquire Bronze

Download the companion `.CHECKSUM` first, then the ZIP. An existing file is
trusted only after a fresh local SHA-256 comparison. A checksum mismatch is a
publication failure and is never allowed into Silver.

## 3. Normalize Silver

The normalizer validates source shape, time units, interval alignment, OHLC,
activity fields, monotonic order, duplicates and gaps. It emits deterministic
CSV.gz files and JSON quality reports.

## 4. Derive Gold

Derive 5m, 15m, 1h and 4h only from a pinned 1m Silver partition. Drop and count
incomplete buckets; never synthesize a missing source bar.

## 5. Build annual distribution assets

`build-full-history-market-data-release` runs a matrix partition for each year.
Each job:

1. plans and checksum-verifies the year's official source candidates;
2. normalizes every available archive;
3. derives all four Gold intervals;
4. rejects unexpected download or checksum statuses;
5. writes a partition catalog and metadata;
6. creates `market-data-<year>-v1.0.0.zip`;
7. records ZIP bytes, SHA-256, file counts and row counts;
8. uploads the ZIP to a draft GitHub Release.

Annual assets are independently retryable and remain below GitHub's single-asset
size boundary. Raw Bronze is not distributed to researchers; its source hashes
and quality evidence are retained in the partition package.

## 6. Publish the distribution index

The final workflow job requires all annual jobs to succeed. It aggregates the
partition manifests into:

```text
full-history-v1.0.0.index.json
full-history-v1.0.0.index.json.sha256
```

Before publishing the draft release, it checks that all ten annual ZIPs and both
index files exist. The index is the sole installation authority used by
`smc-data install`.

A published version is immutable. A corrected source, schema or pipeline creates
a new release ID and tag; assets in an existing published version are not
silently replaced.

## 7. Bundled golden release

The bounded `data/prepared/<release-id>` release is committed in Git to keep CI,
examples and scenario contracts executable without downloading the full history.
Update `data/prepared/CURRENT` only through a reviewed pull request whose CI
verifies every cataloged file.

## 8. Detect upstream revisions

Binance may replace archived objects. A provenance audit re-fetches checksum
files and compares them with the pinned release. A change never mutates an old
release. Instead:

1. record old and new provider checksums;
2. acquire the replacement into a new Bronze build;
3. rerun normalization and quality comparison;
4. explain row-level impact;
5. publish a new GitHub data version.

`audit-golden-source-reproducibility` is explicit/manual and does not run on
every strategy pull request.

## Recovery

A failed annual matrix job leaves the GitHub Release in draft state. Rerun the
failed partition; asset upload uses checksum replacement while the release is
still draft. Publication occurs only after every expected asset is present.

Never edit an installed or published release in place. Local installation uses a
staging directory and atomic rename, so a failed download, extraction or hash
check cannot replace a previously valid dataset.
