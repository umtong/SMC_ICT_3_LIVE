from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import csv
import gzip
import zipfile

import pytest

from smc_ict_data.archive import ArchiveRef, file_sha256
from smc_ict_data.normalization import (
    DataContractError,
    normalize_kline_archive,
    timestamp_to_us,
)


def _ref(kind: str = "kline", dataset: str = "klines") -> ArchiveRef:
    return ArchiveRef(
        archive_id="a" * 20,
        exchange="binance",
        market_path="spot" if kind == "kline" else "futures/um",
        dataset_name="test",
        dataset=dataset,
        kind=kind,
        symbol="BTCUSDT",
        interval="1m",
        period="daily",
        period_start="2024-01-01",
        period_end="2024-01-01",
        url="https://example.test/source.zip",
        checksum_url="https://example.test/source.zip.CHECKSUM",
        relative_path="source.zip",
    )


def _row(open_ms: int, close: str = "101", volume: str = "10") -> list[str]:
    return [
        str(open_ms),
        "100",
        "102",
        "99",
        close,
        volume,
        str(open_ms + 59_999),
        "1000",
        "20",
        "4",
        "400",
        "0",
    ]


def _zip_rows(path: Path, rows: list[list[str]], header: bool = False) -> None:
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if header:
            writer.writerow([
                "open_time", "open", "high", "low", "close", "volume", "close_time",
                "quote_volume", "count", "taker_buy", "taker_quote", "ignore",
            ])
        writer.writerows(rows)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname="data.csv")
    csv_path.unlink()


def _epoch_ms() -> int:
    return int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000)


def test_timestamp_units() -> None:
    assert timestamp_to_us("1704067200") == 1_704_067_200_000_000
    assert timestamp_to_us("1704067200000") == 1_704_067_200_000_000
    assert timestamp_to_us("1704067200000000") == 1_704_067_200_000_000
    assert timestamp_to_us("1704067200000000000") == 1_704_067_200_000_000


def test_normalization_reports_gap_and_removes_exact_duplicate(tmp_path: Path) -> None:
    start = _epoch_ms()
    archive = tmp_path / "source.zip"
    rows = [_row(start), _row(start + 60_000), _row(start + 60_000), _row(start + 180_000)]
    _zip_rows(archive, rows, header=True)
    output = tmp_path / "silver.csv.gz"
    quality = tmp_path / "quality.json"
    report = normalize_kline_archive(
        _ref(), archive, output, quality, expected_sha256=file_sha256(archive)
    )
    assert report.rows_read == 4
    assert report.rows_written == 3
    assert report.exact_duplicates_removed == 1
    assert report.gap_count == 1
    assert report.missing_bar_count == 1

    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        normalized = list(csv.DictReader(handle))
    assert normalized[0]["available_time_us"] == str(int(normalized[0]["open_time_us"]) + 60_000_000)
    assert normalized[0]["base_volume"] == "10"
    assert normalized[0]["source_field_5"] == "10"


def test_reference_kline_does_not_mislabel_auxiliary_fields_as_volume(tmp_path: Path) -> None:
    start = _epoch_ms()
    archive = tmp_path / "reference.zip"
    _zip_rows(archive, [_row(start, volume="0")])
    output = tmp_path / "reference.csv.gz"
    normalize_kline_archive(
        _ref(kind="reference_kline", dataset="markPriceKlines"),
        archive,
        output,
        tmp_path / "quality.json",
    )
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        record = next(csv.DictReader(handle))
    assert record["base_volume"] == ""
    assert record["trade_count"] == ""
    assert record["source_field_5"] == "0"
    assert record["source_field_8"] == "20"


def test_conflicting_duplicate_is_rejected(tmp_path: Path) -> None:
    start = _epoch_ms()
    archive = tmp_path / "bad.zip"
    _zip_rows(archive, [_row(start), _row(start, close="100.5")])
    with pytest.raises(DataContractError, match="conflicting duplicate"):
        normalize_kline_archive(
            _ref(), archive, tmp_path / "out.csv.gz", tmp_path / "quality.json"
        )


def test_output_is_byte_deterministic(tmp_path: Path) -> None:
    start = _epoch_ms()
    archive = tmp_path / "source.zip"
    _zip_rows(archive, [_row(start), _row(start + 60_000)])
    first = tmp_path / "first.csv.gz"
    second = tmp_path / "second.csv.gz"
    normalize_kline_archive(_ref(), archive, first, tmp_path / "first.json")
    normalize_kline_archive(_ref(), archive, second, tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()
