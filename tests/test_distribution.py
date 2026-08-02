from __future__ import annotations

from pathlib import Path
import csv
import json
import zipfile

from smc_ict_data import distribution
from smc_ict_data.catalog import CATALOG_COLUMNS
from smc_ict_data.prepared import file_sha256, load_prepared_release, verify_prepared_release


def _record(path: Path, root: Path) -> dict[str, str | int]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "format": path.suffix.lstrip("."),
        "rows": 0,
        "first_open_time_us": "",
        "last_open_time_us": "",
    }


def _make_partition(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    root = tmp_path / "partition"
    silver = root / "silver" / "binance" / "spot" / "klines" / "BTCUSDT" / "1m" / "2024"
    gold = root / "gold" / "binance" / "spot" / "klines" / "BTCUSDT" / "5m" / "2024"
    quality = root / "quality" / "partitions" / "2024"
    for path in (silver, gold, quality):
        path.mkdir(parents=True)

    silver_file = silver / "BTCUSDT-1m-2024-01.csv.gz"
    gold_file = gold / "BTCUSDT-5m-2024-01.csv.gz"
    quality_file = quality / "report.json"
    silver_file.write_bytes(b"silver")
    gold_file.write_bytes(b"gold")
    quality_file.write_text("{}\n", encoding="utf-8")

    catalog = root / "catalog.csv"
    with catalog.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows([_record(path, root) for path in (silver_file, gold_file, quality_file)])
    (root / "catalog.csv.metadata.json").write_text("{}\n", encoding="utf-8")

    partition = {
        "release_id": "full-history-v1.0.0",
        "partition_id": "2024",
        "catalog_sha256": file_sha256(catalog),
        "files": {"silver": 1, "gold": 1},
        "rows": {"silver": 10, "gold": 2},
    }
    (root / "PARTITION.json").write_text(
        json.dumps(partition, sort_keys=True) + "\n", encoding="utf-8"
    )

    archive = tmp_path / "market-data-2024-v1.0.0.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as handle:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            handle.write(path, path.relative_to(root).as_posix())

    asset = {
        "partition_id": "2024",
        "file": archive.name,
        "url": (
            "https://github.com/umtong/SMC_ICT_3_LIVE/releases/download/"
            "market-data-full-history-v1.0.0/" + archive.name
        ),
        "bytes": archive.stat().st_size,
        "sha256": file_sha256(archive),
        "files": {"silver": 1, "gold": 1},
        "rows": {"silver": 10, "gold": 2},
    }
    return archive, asset


def test_install_distribution_from_verified_partition(tmp_path: Path, monkeypatch) -> None:
    archive, asset = _make_partition(tmp_path)
    index = {
        "release_id": "full-history-v1.0.0",
        "tag": "market-data-full-history-v1.0.0",
        "repository": "umtong/SMC_ICT_3_LIVE",
        "period_utc": "[2017-01-01, 2026-08-01)",
        "symbols": ["BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"],
        "timeframes": ["1m", "5m", "15m", "1h", "4h"],
        "source_datasets": ["spot/klines"],
        "assets": [asset],
    }
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps(index) + "\n", encoding="utf-8")
    monkeypatch.setattr(
        distribution,
        "_download_asset",
        lambda selected, cache_root: archive,
    )

    destination_base = tmp_path / "installed"
    result = distribution.install_distribution(
        index_source=index_path,
        destination_base=destination_base,
        workers=1,
    )

    assert result["status"] == "installed"
    assert (destination_base / "CURRENT").read_text().strip() == "full-history-v1.0.0"
    prepared = load_prepared_release(destination_base)
    assert prepared.metadata["rows"] == {"silver": 10, "gold": 2}
    verification = verify_prepared_release(prepared)
    assert verification["silver_files"] == 1
    assert verification["gold_files"] == 1


def test_distribution_index_rejects_duplicate_partitions(tmp_path: Path) -> None:
    _, asset = _make_partition(tmp_path)
    index = {
        "release_id": "full-history-v1.0.0",
        "tag": "market-data-full-history-v1.0.0",
        "repository": "umtong/SMC_ICT_3_LIVE",
        "period_utc": "[2017-01-01, 2026-08-01)",
        "symbols": ["BTCUSDT"],
        "timeframes": ["1m"],
        "source_datasets": ["spot/klines"],
        "assets": [asset, asset],
    }
    path = tmp_path / "duplicate-index.json"
    path.write_text(json.dumps(index) + "\n", encoding="utf-8")

    try:
        distribution.load_distribution_index(path)
    except ValueError as exc:
        assert "duplicate distribution partition" in str(exc)
    else:
        raise AssertionError("duplicate partition was accepted")
