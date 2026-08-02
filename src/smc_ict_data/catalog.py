from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import csv
import gzip
import json
import os

from .archive import file_sha256


CATALOG_COLUMNS = (
    "relative_path",
    "bytes",
    "sha256",
    "format",
    "rows",
    "first_open_time_us",
    "last_open_time_us",
)


def _inspect_csv_gz(path: Path) -> tuple[int, str, str]:
    rows = 0
    first = ""
    last = ""
    with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if "open_time_us" not in (reader.fieldnames or []):
            return 0, "", ""
        for row in reader:
            value = row["open_time_us"]
            if rows == 0:
                first = value
            last = value
            rows += 1
    return rows, first, last


def build_catalog(root: str | Path, output_path: str | Path) -> Path:
    data_root = Path(root).resolve()
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, str | int]] = []
    for path in sorted(item for item in data_root.rglob("*") if item.is_file()):
        if path.resolve() == destination.resolve():
            continue
        suffix = "".join(path.suffixes[-2:]) if path.name.endswith(".csv.gz") else path.suffix
        rows = 0
        first = ""
        last = ""
        if path.name.endswith(".csv.gz"):
            rows, first, last = _inspect_csv_gz(path)
        records.append(
            {
                "relative_path": path.relative_to(data_root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
                "format": suffix.lstrip("."),
                "rows": rows,
                "first_open_time_us": first,
                "last_open_time_us": last,
            }
        )

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    os.replace(temporary, destination)

    metadata = {
        "catalog_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "root": data_root.as_posix(),
        "file_count": len(records),
        "catalog_sha256": file_sha256(destination),
    }
    metadata_path = destination.with_suffix(destination.suffix + ".metadata.json")
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return destination
