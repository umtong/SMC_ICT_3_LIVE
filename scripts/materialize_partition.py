from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import gzip
import json
import shutil

from smc_ict_data.archive import file_sha256
from smc_ict_data.catalog import build_catalog
from smc_ict_data.normalization import PIPELINE_VERSION
from smc_ict_data.resample import resample_file


TARGET_INTERVALS = ("5m", "15m", "1h", "4h")
ACCEPTED_DOWNLOAD_STATUSES = {"downloaded_verified", "verified_existing", "source_unavailable"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize one validated, mergeable full-history release partition"
    )
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--partition-id", required=True)
    parser.add_argument("--period-utc", required=True)
    parser.add_argument("--repository-commit", required=True)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def count_csv_rows(root: Path) -> tuple[int, int]:
    files = sorted(root.rglob("*.csv.gz"))
    rows = 0
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            next(handle, None)
            rows += sum(1 for _ in handle)
    return len(files), rows


def read_download_statuses(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            counts[str(payload["status"])] += 1
    unexpected = sorted(set(counts) - ACCEPTED_DOWNLOAD_STATUSES)
    if unexpected:
        raise RuntimeError(f"partition contains rejected download statuses: {unexpected}")
    return counts


def summarize_normalization_quality(root: Path) -> dict[str, int]:
    totals: Counter[str] = Counter()
    maximum_early_us = 0
    report_count = 0
    for path in sorted(root.rglob("*.quality.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        report_count += 1
        for field in (
            "rows_read",
            "rows_written",
            "exact_duplicates_removed",
            "gap_count",
            "missing_bar_count",
            "source_close_time_anomaly_count",
        ):
            totals[field] += int(payload.get(field, 0))
        maximum_early_us = max(
            maximum_early_us,
            int(payload.get("source_close_time_max_early_us", 0)),
        )
    return {
        "normalization_reports": report_count,
        **dict(sorted(totals.items())),
        "source_close_time_max_early_us": maximum_early_us,
    }


def derived_paths(
    source: Path,
    silver_root: Path,
    gold_root: Path,
    quality_root: Path,
    target: str,
) -> tuple[Path, Path]:
    relative = source.relative_to(silver_root)
    parts = list(relative.parts)
    try:
        interval_index = parts.index("1m")
    except ValueError as exc:
        raise RuntimeError(f"1m interval directory missing from {relative}") from exc

    parts[interval_index] = target
    if "-1m-" not in parts[-1]:
        raise RuntimeError(f"1m filename token missing from {relative}")
    parts[-1] = parts[-1].replace("-1m-", f"-{target}-", 1)

    destination = gold_root.joinpath(*parts)
    report_name = parts[-1].removesuffix(".csv.gz") + ".quality.json"
    report = quality_root / "resample" / Path(*parts[:-1]) / report_name
    return destination, report


def make_catalog_portable(catalog: Path) -> None:
    metadata_path = catalog.with_suffix(catalog.suffix + ".metadata.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["root"] = "."
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def materialize(args: argparse.Namespace) -> dict[str, object]:
    work_root = args.work_root.resolve()
    manifest = args.manifest.resolve()
    output_root = args.output_root.resolve()
    if output_root.exists():
        if not args.force:
            raise FileExistsError(f"output already exists: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    source_silver = work_root / "02_NORMALIZED_SILVER"
    source_quality = work_root / "04_CATALOG_QUALITY"
    download_report = source_quality / "download_report.jsonl"
    if not source_silver.is_dir() or not download_report.is_file():
        raise FileNotFoundError("work root does not contain a completed smc-data build")

    silver_root = output_root / "silver"
    gold_root = output_root / "gold"
    partition_quality = output_root / "quality" / "partitions" / args.partition_id
    shutil.copytree(source_silver, silver_root)
    partition_quality.mkdir(parents=True)
    shutil.copy2(download_report, partition_quality / "download_report.jsonl")
    shutil.copy2(manifest, partition_quality / "source_manifest.csv")
    normalization = source_quality / "normalization"
    if normalization.is_dir():
        shutil.copytree(normalization, partition_quality / "normalization")

    contracts = partition_quality / "contracts"
    contracts.mkdir()
    for name in ("DATA_CONTRACT.md", "BACKTEST_SEMANTICS.md"):
        shutil.copy2(Path("docs") / name, contracts / name)

    download_counts = read_download_statuses(download_report)
    normalization_quality = summarize_normalization_quality(normalization)
    for source in sorted(silver_root.rglob("*.csv.gz")):
        for target in TARGET_INTERVALS:
            destination, report = derived_paths(
                source,
                silver_root,
                gold_root,
                partition_quality,
                target,
            )
            resample_file(source, destination, report, target_interval=target)

    silver_files, silver_rows = count_csv_rows(silver_root)
    gold_files, gold_rows = count_csv_rows(gold_root)
    if silver_files == 0 or silver_rows == 0:
        raise RuntimeError(f"partition {args.partition_id} contains no verified Silver data")
    if gold_files != silver_files * len(TARGET_INTERVALS):
        raise RuntimeError(
            f"Gold file count mismatch: silver={silver_files}, gold={gold_files}, "
            f"targets={len(TARGET_INTERVALS)}"
        )

    catalog = build_catalog(output_root, output_root / "catalog.csv")
    make_catalog_portable(catalog)
    metadata = {
        "schema_version": "1.0",
        "release_id": args.release_id,
        "partition_id": args.partition_id,
        "status": "ready",
        "period_utc": args.period_utc,
        "symbols": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"],
        "source_datasets": [
            "spot/klines",
            "futures/um/klines",
            "futures/um/markPriceKlines",
            "futures/um/indexPriceKlines",
            "futures/um/premiumIndexKlines",
        ],
        "base_interval": "1m",
        "timeframes": ["1m", *TARGET_INTERVALS],
        "files": {"silver": silver_files, "gold": gold_files},
        "rows": {"silver": silver_rows, "gold": gold_rows},
        "download_statuses": dict(sorted(download_counts.items())),
        "normalization_quality": normalization_quality,
        "catalog_sha256": file_sha256(catalog),
        "source_manifest_sha256": file_sha256(partition_quality / "source_manifest.csv"),
        "pipeline_version": PIPELINE_VERSION,
        "repository_commit": args.repository_commit,
        "external_runtime_dependency": False,
        "external_data_download_required_after_publication": False,
    }
    (output_root / "PARTITION.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def main() -> int:
    args = parse_args()
    metadata = materialize(args)
    print(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
