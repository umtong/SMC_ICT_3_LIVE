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
            writer.writerow(
                [
                    "open_time",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "close_time",
                    "quote_volume",
                    "count",
                    "taker_buy",
                    "taker_quote",
                    "ignore",
                ]
            )
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
    assert report.source_close_time_anomaly_count == 0

    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        normalized = list(csv.DictReader(handle))
    assert normalized[0]["available_time_us"] == str(
        int(normalized[0]["open_time_us"]) + 60_000_000
    )
    assert normalized[0]["base_volume"] == "10"
    assert normalized[0]["source_field_5"] == "10"


def test_historical_in_bar_source_close_is_preserved_and_reported(tmp_path: Path) -> None:
    start = _epoch_ms()
    historical = _row(start)
    historical[6] = str(start + 20_809)
    archive = tmp_path / "historical.zip"
    _zip_rows(archive, [historical])
    output = tmp_path / "historical.csv.gz"

    report = normalize_kline_archive(_ref(), archive, output, tmp_path / "historical.quality.json")

    assert report.source_close_time_anomaly_count == 1
    assert report.source_close_time_max_early_us == 39_191_000
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        record = next(csv.DictReader(handle))
    assert record["source_close_time_us"] == str((start + 20_809) * 1_000)
    assert record["available_time_us"] == str(start * 1_000 + 60_000_000)


def test_source_close_crossing_interval_is_quarantined(tmp_path: Path) -> None:
    start = _epoch_ms()
    invalid = _row(start)
    invalid[6] = str(start + 60_001)
    archive = tmp_path / "invalid-close.zip"
    _zip_rows(archive, [invalid])

    output = tmp_path / "invalid.csv.gz"
    report = normalize_kline_archive(
        _ref(),
        archive,
        output,
        tmp_path / "invalid.quality.json",
    )

    assert report.rows_read == 1
    assert report.rows_written == 0
    assert report.quarantined_source_row_count == 1
    assert report.quarantined_canonical_bar_count == 1
    assert report.source_close_time_late_count == 1
    assert report.status == "valid_with_quarantine"
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        assert list(csv.DictReader(handle)) == []


def test_historical_segmented_minute_is_losslessly_merged(tmp_path: Path) -> None:
    start = _epoch_ms()
    first = _row(start)
    first[1:5] = ["100", "102", "99", "100.5"]
    first[5] = "2"
    first[6] = str(start + 20_809)
    first[7:11] = ["200", "3", "1", "100"]

    second = _row(start + 20_810)
    second[1:5] = ["100.5", "103", "100", "102"]
    second[5] = "3"
    second[6] = str(start + 59_999)
    second[7:11] = ["310", "4", "2", "205"]

    archive = tmp_path / "segmented.zip"
    _zip_rows(archive, [first, second])
    output = tmp_path / "segmented.csv.gz"
    report = normalize_kline_archive(_ref(), archive, output, tmp_path / "segmented.quality.json")

    assert report.rows_read == 2
    assert report.rows_written == 1
    assert report.segmented_bar_count == 1
    assert report.segmented_source_rows_merged == 1
    assert report.source_open_time_anomaly_count == 1
    assert report.quarantined_canonical_bar_count == 0
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        record = next(csv.DictReader(handle))
    assert record["open_time_us"] == str(start * 1_000)
    assert record["available_time_us"] == str(start * 1_000 + 60_000_000)
    assert record["open"] == "100"
    assert record["high"] == "103"
    assert record["low"] == "99"
    assert record["close"] == "102"
    assert record["base_volume"] == "5"
    assert record["quote_volume"] == "510"
    assert record["trade_count"] == "7"
    assert record["taker_buy_base_volume"] == "3"
    assert record["taker_buy_quote_volume"] == "305"


def test_source_close_before_open_is_quarantined(tmp_path: Path) -> None:
    start = _epoch_ms()
    invalid = _row(start)
    invalid[6] = str(start - 1)
    archive = tmp_path / "close-before-open.zip"
    _zip_rows(archive, [invalid])

    report = normalize_kline_archive(
        _ref(),
        archive,
        tmp_path / "close-before-open.csv.gz",
        tmp_path / "close-before-open.quality.json",
    )

    assert report.rows_written == 0
    assert report.quarantined_canonical_bar_count == 1
    assert report.status == "valid_with_quarantine"
    assert report.anomaly_examples[0].reason == "source_close_before_open"


def test_unaligned_row_without_bucket_start_is_quarantined(tmp_path: Path) -> None:
    start = _epoch_ms()
    orphan = _row(start + 20_810)
    orphan[6] = str(start + 59_999)
    archive = tmp_path / "orphan-segment.zip"
    _zip_rows(archive, [orphan])

    report = normalize_kline_archive(
        _ref(),
        archive,
        tmp_path / "orphan-segment.csv.gz",
        tmp_path / "orphan-segment.quality.json",
    )

    assert report.rows_written == 0
    assert report.source_open_time_anomaly_count == 1
    assert report.quarantined_canonical_bar_count == 1


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


def test_premium_index_allows_negative_values_but_mark_price_does_not(
    tmp_path: Path,
) -> None:
    start = _epoch_ms()
    negative = _row(start)
    negative[1:5] = ["-0.001", "0.001", "-0.002", "-0.0005"]
    archive = tmp_path / "negative_reference.zip"
    _zip_rows(archive, [negative])

    normalize_kline_archive(
        _ref(kind="reference_kline", dataset="premiumIndexKlines"),
        archive,
        tmp_path / "premium.csv.gz",
        tmp_path / "premium.json",
    )

    with pytest.raises(DataContractError, match="negative price"):
        normalize_kline_archive(
            _ref(kind="reference_kline", dataset="markPriceKlines"),
            archive,
            tmp_path / "mark.csv.gz",
            tmp_path / "mark.json",
        )


def test_conflicting_duplicate_is_rejected(tmp_path: Path) -> None:
    start = _epoch_ms()
    archive = tmp_path / "bad.zip"
    _zip_rows(archive, [_row(start), _row(start, close="100.5")])
    with pytest.raises(DataContractError, match="conflicting duplicate"):
        normalize_kline_archive(_ref(), archive, tmp_path / "out.csv.gz", tmp_path / "quality.json")


def test_output_is_byte_deterministic(tmp_path: Path) -> None:
    start = _epoch_ms()
    archive = tmp_path / "source.zip"
    _zip_rows(archive, [_row(start), _row(start + 60_000)])
    first = tmp_path / "first.csv.gz"
    second = tmp_path / "second.csv.gz"
    normalize_kline_archive(_ref(), archive, first, tmp_path / "first.json")
    normalize_kline_archive(_ref(), archive, second, tmp_path / "second.json")
    assert first.read_bytes() == second.read_bytes()
