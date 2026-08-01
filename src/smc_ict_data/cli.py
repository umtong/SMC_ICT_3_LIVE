from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence
import argparse
import json
import sys

from .archive import download_manifest, plan_archives, write_manifest
from .catalog import build_catalog
from .model import load_config, parse_date, resolve_history_end
from .normalization import normalize_manifest
from .resample import resample_file


DEFAULT_CONFIG = Path("configs/market_data.toml")


def _date_or_none(value: str | None):
    return parse_date(value) if value else None


def _emit(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def command_plan(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    start = _date_or_none(args.start) or config.history_start
    end = _date_or_none(args.end) or resolve_history_end(config.history_end)
    as_of = _date_or_none(args.as_of) or datetime.now(timezone.utc).date()
    refs = plan_archives(
        config,
        start,
        end,
        as_of,
        include_disabled=args.include_disabled,
    )
    output = write_manifest(refs, args.out)
    _emit(
        {
            "status": "planned",
            "manifest": output.as_posix(),
            "candidate_archives": len(refs),
            "symbols": list(config.symbols),
            "datasets": sorted({item.dataset_name for item in refs}),
            "start": start,
            "end": end,
            "as_of": as_of,
            "important": "candidate URLs are availability-verified during download; 404 is recorded, not guessed",
        }
    )
    return 0


def command_download(args: argparse.Namespace) -> int:
    results = download_manifest(
        args.manifest,
        args.raw_root,
        args.report,
        workers=args.workers,
        retries=args.retries,
        timeout=args.timeout,
    )
    counts = Counter(item.status for item in results)
    _emit({"status": "complete", "report": args.report, "counts": dict(sorted(counts.items()))})
    return 1 if any(name.startswith("failed") for name in counts) else 0


def command_normalize(args: argparse.Namespace) -> int:
    reports = normalize_manifest(
        args.manifest,
        args.download_report,
        args.raw_root,
        args.silver_root,
        args.quality_root,
    )
    _emit(
        {
            "status": "normalized",
            "archives": len(reports),
            "rows": sum(item.rows_written for item in reports),
            "missing_bars_reported": sum(item.missing_bar_count for item in reports),
        }
    )
    return 0


def command_build(args: argparse.Namespace) -> int:
    download_results = download_manifest(
        args.manifest,
        args.raw_root,
        args.download_report,
        workers=args.workers,
        retries=args.retries,
        timeout=args.timeout,
    )
    counts = Counter(item.status for item in download_results)
    if any(name.startswith("failed") for name in counts):
        _emit(
            {
                "status": "download_failed",
                "counts": dict(sorted(counts.items())),
                "download_report": args.download_report,
            }
        )
        return 1
    reports = normalize_manifest(
        args.manifest,
        args.download_report,
        args.raw_root,
        args.silver_root,
        args.quality_root,
    )
    catalog = build_catalog(args.data_root, args.catalog)
    _emit(
        {
            "status": "built",
            "download_counts": dict(sorted(counts.items())),
            "normalized_archives": len(reports),
            "normalized_rows": sum(item.rows_written for item in reports),
            "catalog": catalog.as_posix(),
        }
    )
    return 0


def command_resample(args: argparse.Namespace) -> int:
    report = resample_file(
        args.input,
        args.output,
        args.report,
        target_interval=args.target,
    )
    _emit(asdict(report))
    return 0


def command_catalog(args: argparse.Namespace) -> int:
    output = build_catalog(args.root, args.out)
    _emit({"status": "cataloged", "catalog": output.as_posix()})
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    optional: dict[str, bool] = {}
    for package in ("duckdb", "pyarrow"):
        try:
            __import__(package)
            optional[package] = True
        except ImportError:
            optional[package] = False
    _emit(
        {
            "status": "ok",
            "python": sys.version.split()[0],
            "config_version": config.version,
            "symbols": list(config.symbols),
            "enabled_datasets": [item.name for item in config.enabled_datasets],
            "optional_packages": optional,
            "note": "optional packages are not required for planning, downloading, validation or CSV.gz builds",
        }
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="smc-data",
        description="Reproducible Binance market-data pipeline for SMC/ICT research",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan", help="write deterministic candidate archive manifest")
    plan.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    plan.add_argument("--start", help="inclusive YYYY-MM-DD; defaults to config")
    plan.add_argument("--end", help="inclusive YYYY-MM-DD; defaults to latest complete UTC day")
    plan.add_argument("--as-of", help="planning knowledge date, YYYY-MM-DD")
    plan.add_argument("--include-disabled", action="store_true")
    plan.add_argument("--out", type=Path, required=True)
    plan.set_defaults(handler=command_plan)

    download = subparsers.add_parser("download", help="download and checksum-verify Bronze archives")
    download.add_argument("--manifest", type=Path, required=True)
    download.add_argument("--raw-root", type=Path, required=True)
    download.add_argument("--report", type=Path, required=True)
    download.add_argument("--workers", type=int, default=4)
    download.add_argument("--retries", type=int, default=4)
    download.add_argument("--timeout", type=float, default=60.0)
    download.set_defaults(handler=command_download)

    normalize = subparsers.add_parser("normalize", help="validate and normalize verified archives")
    normalize.add_argument("--manifest", type=Path, required=True)
    normalize.add_argument("--download-report", type=Path, required=True)
    normalize.add_argument("--raw-root", type=Path, required=True)
    normalize.add_argument("--silver-root", type=Path, required=True)
    normalize.add_argument("--quality-root", type=Path, required=True)
    normalize.set_defaults(handler=command_normalize)

    build = subparsers.add_parser("build", help="download, normalize and catalog one manifest")
    build.add_argument("--manifest", type=Path, required=True)
    build.add_argument("--data-root", type=Path, required=True)
    build.add_argument("--raw-root", type=Path, required=True)
    build.add_argument("--silver-root", type=Path, required=True)
    build.add_argument("--quality-root", type=Path, required=True)
    build.add_argument("--download-report", type=Path, required=True)
    build.add_argument("--catalog", type=Path, required=True)
    build.add_argument("--workers", type=int, default=4)
    build.add_argument("--retries", type=int, default=4)
    build.add_argument("--timeout", type=float, default=60.0)
    build.set_defaults(handler=command_build)

    resample = subparsers.add_parser("resample", help="derive a complete higher timeframe")
    resample.add_argument("--input", type=Path, required=True)
    resample.add_argument("--target", required=True, help="for example 5m, 15m, 1h, 4h")
    resample.add_argument("--output", type=Path, required=True)
    resample.add_argument("--report", type=Path, required=True)
    resample.set_defaults(handler=command_resample)

    catalog = subparsers.add_parser("catalog", help="hash and index a data-tree release")
    catalog.add_argument("--root", type=Path, required=True)
    catalog.add_argument("--out", type=Path, required=True)
    catalog.set_defaults(handler=command_catalog)

    doctor = subparsers.add_parser("doctor", help="check configuration and optional tooling")
    doctor.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    doctor.set_defaults(handler=command_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
