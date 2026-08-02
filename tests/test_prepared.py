from __future__ import annotations

from pathlib import Path
import csv
import json

import pytest

from smc_ict_data.prepared import file_sha256, load_prepared_release, verify_prepared_release


def _make_release(tmp_path: Path) -> Path:
    base = tmp_path / "prepared"
    release_id = "fixture-v1"
    release = base / release_id
    silver = release / "silver"
    gold = release / "gold"
    quality = release / "quality"
    for path in (silver, gold, quality):
        path.mkdir(parents=True)

    silver_file = silver / "sample.csv.gz"
    gold_file = gold / "sample-5m.csv.gz"
    quality_file = quality / "report.json"
    silver_file.write_bytes(b"silver")
    gold_file.write_bytes(b"gold")
    quality_file.write_text("{}\n", encoding="utf-8")

    catalog = release / "catalog.csv"
    with catalog.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "relative_path",
                "bytes",
                "sha256",
                "format",
                "rows",
                "first_open_time_us",
                "last_open_time_us",
            ),
            lineterminator="\n",
        )
        writer.writeheader()
        for file in (silver_file, gold_file, quality_file):
            writer.writerow(
                {
                    "relative_path": file.relative_to(release).as_posix(),
                    "bytes": file.stat().st_size,
                    "sha256": file_sha256(file),
                    "format": file.suffix.lstrip("."),
                    "rows": 0,
                    "first_open_time_us": "",
                    "last_open_time_us": "",
                }
            )

    metadata = {
        "release_id": release_id,
        "status": "ready",
        "period_utc": "[2024-01-01, 2024-02-01)",
        "symbols": ["BTCUSDT"],
        "timeframes": ["1m", "5m"],
        "files": {"silver": 1, "gold": 1},
        "rows": {"silver": 1, "gold": 1},
        "external_runtime_dependency": False,
        "catalog_sha256": file_sha256(catalog),
        "paths": {
            "silver": "silver",
            "gold": "gold",
            "quality": "quality",
            "catalog": "catalog.csv",
        },
    }
    (release / "PREPARED_DATA.json").write_text(
        json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8"
    )
    base.mkdir(parents=True, exist_ok=True)
    (base / "CURRENT").write_text(release_id + "\n", encoding="utf-8")
    return base


def test_load_and_verify_prepared_release(tmp_path: Path) -> None:
    base = _make_release(tmp_path)
    prepared = load_prepared_release(base)

    assert prepared.release_id == "fixture-v1"
    assert prepared.summary()["external_runtime_dependency"] is False
    verification = verify_prepared_release(prepared)
    assert verification["status"] == "verified"
    assert verification["cataloged_files_checked"] == 3
    assert verification["silver_files"] == 1
    assert verification["gold_files"] == 1


def test_specific_release_root_is_supported(tmp_path: Path) -> None:
    base = _make_release(tmp_path)
    prepared = load_prepared_release(base / "fixture-v1")
    assert prepared.release_id == "fixture-v1"


def test_verification_rejects_mutation(tmp_path: Path) -> None:
    base = _make_release(tmp_path)
    prepared = load_prepared_release(base)
    next(prepared.silver_root.rglob("*.csv.gz")).write_bytes(b"mutated")

    with pytest.raises(ValueError, match="size mismatch|checksum mismatch"):
        verify_prepared_release(prepared)
