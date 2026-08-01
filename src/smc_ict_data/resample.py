from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable
import csv
import gzip
import io
import json
import os

from .archive import file_sha256
from .normalization import KLINE_OUTPUT_COLUMNS, PIPELINE_VERSION, interval_to_us


DERIVED_OUTPUT_COLUMNS = KLINE_OUTPUT_COLUMNS + ("source_bar_count", "is_complete")


@dataclass(frozen=True, slots=True)
class ResampleReport:
    input_path: str
    input_sha256: str
    output_path: str
    output_sha256: str
    source_interval: str
    target_interval: str
    source_rows: int
    output_rows: int
    incomplete_buckets_dropped: int
    status: str = "valid"
    pipeline_version: str = PIPELINE_VERSION


def _sum_decimal(rows: list[dict[str, str]], field: str) -> str:
    values = [item[field] for item in rows]
    if any(value == "" for value in values):
        return ""
    return format(sum((Decimal(value) for value in values), Decimal(0)), "f")


def _sum_integer(rows: list[dict[str, str]], field: str) -> str:
    values = [item[field] for item in rows]
    if any(value == "" for value in values):
        return ""
    return str(sum(int(value) for value in values))


def _bucket_complete(
    rows: list[dict[str, str]], bucket_start: int, source_us: int, expected_count: int
) -> bool:
    if len(rows) != expected_count:
        return False
    expected = [bucket_start + index * source_us for index in range(expected_count)]
    actual = [int(item["open_time_us"]) for item in rows]
    return actual == expected


def _aggregate_bucket(
    rows: list[dict[str, str]], bucket_start: int, target_interval: str, target_us: int
) -> dict[str, str | int]:
    first = rows[0]
    last = rows[-1]
    high = max(Decimal(item["high"]) for item in rows)
    low = min(Decimal(item["low"]) for item in rows)
    input_hashes = sorted({item["source_sha256"] for item in rows})
    provenance = ",".join(input_hashes)
    record: dict[str, str | int] = {
        **{column: first.get(column, "") for column in KLINE_OUTPUT_COLUMNS},
        "interval": target_interval,
        "open_time_us": bucket_start,
        "close_time_exclusive_us": bucket_start + target_us,
        "available_time_us": bucket_start + target_us,
        "source_close_time_us": "",
        "open": first["open"],
        "high": format(high, "f"),
        "low": format(low, "f"),
        "close": last["close"],
        "base_volume": _sum_decimal(rows, "base_volume"),
        "quote_volume": _sum_decimal(rows, "quote_volume"),
        "trade_count": _sum_integer(rows, "trade_count"),
        "taker_buy_base_volume": _sum_decimal(rows, "taker_buy_base_volume"),
        "taker_buy_quote_volume": _sum_decimal(rows, "taker_buy_quote_volume"),
        "source_field_5": "",
        "source_field_7": "",
        "source_field_8": "",
        "source_field_9": "",
        "source_field_10": "",
        "source_field_11": "",
        "source_url": f"derived://sha256/{file_sha256_text(provenance)}",
        "source_sha256": file_sha256_text(provenance),
        "archive_id": "derived",
        "pipeline_version": PIPELINE_VERSION,
        "source_bar_count": len(rows),
        "is_complete": "true",
    }
    return record


def file_sha256_text(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode("utf-8")).hexdigest()


def resample_file(
    input_path: str | Path,
    output_path: str | Path,
    report_path: str | Path,
    *,
    target_interval: str,
) -> ResampleReport:
    source = Path(input_path)
    destination = Path(output_path)
    report_destination = Path(report_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report_destination.parent.mkdir(parents=True, exist_ok=True)
    input_hash = file_sha256(source)

    with gzip.open(source, "rt", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError("input contains no rows")
    source_intervals = {row["interval"] for row in rows}
    if len(source_intervals) != 1:
        raise ValueError(f"input mixes intervals: {sorted(source_intervals)}")
    source_interval = next(iter(source_intervals))
    source_us = interval_to_us(source_interval)
    target_us = interval_to_us(target_interval)
    if target_us <= source_us or target_us % source_us:
        raise ValueError("target interval must be an integer multiple larger than source interval")
    expected_count = target_us // source_us

    buckets: dict[int, list[dict[str, str]]] = {}
    previous: int | None = None
    for row in rows:
        open_time = int(row["open_time_us"])
        if previous is not None and open_time <= previous:
            raise ValueError("input must be strictly increasing")
        previous = open_time
        bucket_start = (open_time // target_us) * target_us
        buckets.setdefault(bucket_start, []).append(row)

    temporary = destination.with_suffix(destination.suffix + ".tmp")
    binary = temporary.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    output_rows = 0
    dropped = 0
    try:
        writer = csv.DictWriter(text, fieldnames=DERIVED_OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for bucket_start in sorted(buckets):
            bucket = buckets[bucket_start]
            if not _bucket_complete(bucket, bucket_start, source_us, expected_count):
                dropped += 1
                continue
            writer.writerow(_aggregate_bucket(bucket, bucket_start, target_interval, target_us))
            output_rows += 1
        text.flush()
        text.close()
        binary.close()
    except Exception:
        try:
            text.close()
        finally:
            binary.close()
        temporary.unlink(missing_ok=True)
        raise
    os.replace(temporary, destination)

    report = ResampleReport(
        input_path=source.as_posix(),
        input_sha256=input_hash,
        output_path=destination.as_posix(),
        output_sha256=file_sha256(destination),
        source_interval=source_interval,
        target_interval=target_interval,
        source_rows=len(rows),
        output_rows=output_rows,
        incomplete_buckets_dropped=dropped,
    )
    temporary_report = report_destination.with_suffix(report_destination.suffix + ".tmp")
    temporary_report.write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_report, report_destination)
    return report
