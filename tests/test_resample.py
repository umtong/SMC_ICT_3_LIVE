from datetime import datetime, timezone
from pathlib import Path
import csv
import gzip
import zipfile

from smc_ict_data.archive import ArchiveRef
from smc_ict_data.normalization import normalize_kline_archive
from smc_ict_data.resample import resample_file


def _make_archive(path: Path, count: int, missing_index: int | None = None) -> ArchiveRef:
    start = int(datetime(2024, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000)
    rows: list[list[str]] = []
    for index in range(count):
        if index == missing_index:
            continue
        open_ms = start + index * 60_000
        price = 100 + index
        rows.append([
            str(open_ms), str(price), str(price + 1), str(price - 1), str(price + 0.5),
            "1", str(open_ms + 59_999), "100", "2", "0.4", "40", "0",
        ])
    csv_path = path.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, lineterminator="\n").writerows(rows)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(csv_path, arcname="data.csv")
    csv_path.unlink()
    return ArchiveRef(
        archive_id="b" * 20,
        exchange="binance",
        market_path="spot",
        dataset_name="spot_klines",
        dataset="klines",
        kind="kline",
        symbol="BTCUSDT",
        interval="1m",
        period="daily",
        period_start="2024-01-01",
        period_end="2024-01-01",
        url="https://example.test/source.zip",
        checksum_url="https://example.test/source.zip.CHECKSUM",
        relative_path="source.zip",
    )


def test_resample_only_writes_complete_buckets(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    ref = _make_archive(archive, 10, missing_index=7)
    silver = tmp_path / "one_minute.csv.gz"
    normalize_kline_archive(ref, archive, silver, tmp_path / "source_quality.json")
    output = tmp_path / "five_minute.csv.gz"
    report = resample_file(
        silver,
        output,
        tmp_path / "resample_quality.json",
        target_interval="5m",
    )
    assert report.source_rows == 9
    assert report.output_rows == 1
    assert report.incomplete_buckets_dropped == 1
    with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
        record = next(csv.DictReader(handle))
    assert record["open"] == "100"
    assert record["close"] == "104.5"
    assert record["high"] == "105"
    assert record["low"] == "99"
    assert record["base_volume"] == "5"
    assert record["source_bar_count"] == "5"
