from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator, TextIO
import csv
import gzip
import io
import json
import os
import zipfile

from .archive import ArchiveRef, DownloadResult, file_sha256, read_manifest
from .canonicalize import (
    CanonicalizationStats,
    SourceCanonicalizationError,
    SourceTimeAnomaly,
    canonicalize_kline_rows,
)


PIPELINE_VERSION = "1.0.2"
KLINE_OUTPUT_COLUMNS = (
    "exchange",
    "market_path",
    "dataset",
    "dataset_kind",
    "symbol",
    "interval",
    "open_time_us",
    "close_time_exclusive_us",
    "available_time_us",
    "source_close_time_us",
    "open",
    "high",
    "low",
    "close",
    "base_volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
    "source_field_5",
    "source_field_7",
    "source_field_8",
    "source_field_9",
    "source_field_10",
    "source_field_11",
    "source_url",
    "source_sha256",
    "archive_id",
    "pipeline_version",
)


@dataclass(frozen=True, slots=True)
class Gap:
    after_open_time_us: int
    before_open_time_us: int
    missing_bars: int


@dataclass(frozen=True, slots=True)
class QualityReport:
    archive_id: str
    dataset: str
    symbol: str
    interval: str
    source_url: str
    source_sha256: str
    output_path: str
    output_sha256: str
    rows_read: int
    rows_written: int
    exact_duplicates_removed: int
    gap_count: int
    missing_bar_count: int
    first_open_time_us: int | None
    last_open_time_us: int | None
    requested_start: str
    requested_end: str
    gaps: tuple[Gap, ...]
    source_close_time_anomaly_count: int = 0
    source_close_time_max_early_us: int = 0
    source_open_time_anomaly_count: int = 0
    source_open_time_max_late_us: int = 0
    source_close_time_late_count: int = 0
    source_close_time_max_late_us: int = 0
    segmented_bar_count: int = 0
    segmented_source_rows_merged: int = 0
    quarantined_source_row_count: int = 0
    quarantined_canonical_bar_count: int = 0
    anomaly_examples: tuple[SourceTimeAnomaly, ...] = ()
    status: str = "valid"
    pipeline_version: str = PIPELINE_VERSION


class DataContractError(ValueError):
    pass


def interval_to_us(interval: str) -> int:
    if len(interval) < 2:
        raise DataContractError(f"invalid interval: {interval!r}")
    unit = interval[-1]
    try:
        amount = int(interval[:-1])
    except ValueError as exc:
        raise DataContractError(f"invalid interval: {interval!r}") from exc
    multipliers = {
        "s": 1_000_000,
        "m": 60_000_000,
        "h": 3_600_000_000,
        "d": 86_400_000_000,
        "w": 604_800_000_000,
    }
    if unit not in multipliers or amount <= 0:
        raise DataContractError(f"unsupported fixed interval: {interval!r}")
    return amount * multipliers[unit]


def timestamp_to_us(value: str | int) -> int:
    """Normalize seconds/milliseconds/microseconds/nanoseconds to integer microseconds."""

    try:
        raw = int(value)
    except (TypeError, ValueError) as exc:
        raise DataContractError(f"invalid integer timestamp: {value!r}") from exc
    magnitude = abs(raw)
    if magnitude >= 100_000_000_000_000_000:  # nanoseconds
        return raw // 1_000
    if magnitude >= 100_000_000_000_000:  # microseconds
        return raw
    if magnitude >= 100_000_000_000:  # milliseconds
        return raw * 1_000
    if magnitude >= 1_000_000_000:  # seconds
        return raw * 1_000_000
    raise DataContractError(f"timestamp magnitude is not a supported Unix unit: {value!r}")


def _utc_day_bounds(start: str, end: str) -> tuple[int, int]:
    start_day = date.fromisoformat(start)
    end_day = date.fromisoformat(end)
    start_dt = datetime.combine(start_day, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    return int(start_dt.timestamp() * 1_000_000), int(end_dt.timestamp() * 1_000_000)


def _is_header(row: list[str]) -> bool:
    if not row:
        return False
    try:
        int(row[0])
        return False
    except ValueError:
        return True


def _archive_rows(path: Path) -> Iterator[list[str]]:
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if not name.endswith("/")]
        csv_members = [name for name in members if name.lower().endswith(".csv")]
        if len(csv_members) != 1:
            raise DataContractError(
                f"expected exactly one CSV member in {path}, found {len(csv_members)}"
            )
        with archive.open(csv_members[0], "r") as raw:
            with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
                reader = csv.reader(text)
                first = next(reader, None)
                if first is None:
                    return
                if not _is_header(first):
                    yield first
                yield from reader


def _decimal(value: str, field: str) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise DataContractError(f"{field} is not decimal: {value!r}") from exc
    if not result.is_finite():
        raise DataContractError(f"{field} must be finite: {value!r}")
    return result


def _validate_ohlc(row: list[str], line_number: int, *, allow_negative: bool = False) -> None:
    open_price = _decimal(row[1], "open")
    high = _decimal(row[2], "high")
    low = _decimal(row[3], "low")
    close = _decimal(row[4], "close")
    if not allow_negative and min(open_price, high, low, close) < 0:
        raise DataContractError(f"negative price at source row {line_number}")
    if high < max(open_price, low, close):
        raise DataContractError(f"high violates OHLC ordering at source row {line_number}")
    if low > min(open_price, high, close):
        raise DataContractError(f"low violates OHLC ordering at source row {line_number}")


def _validate_trade_fields(row: list[str], line_number: int) -> None:
    for index, field in (
        (5, "base_volume"),
        (7, "quote_volume"),
        (9, "taker_buy_base"),
        (10, "taker_buy_quote"),
    ):
        if _decimal(row[index], field) < 0:
            raise DataContractError(f"negative {field} at source row {line_number}")
    try:
        trade_count = int(row[8])
    except ValueError as exc:
        raise DataContractError(f"trade count is not integer at source row {line_number}") from exc
    if trade_count < 0:
        raise DataContractError(f"negative trade count at source row {line_number}")


def _open_deterministic_gzip_text(path: Path) -> tuple[TextIO, TextIO]:
    """Return text wrapper and underlying binary handle; caller closes both."""

    binary = path.open("wb")
    compressed = gzip.GzipFile(filename="", mode="wb", fileobj=binary, mtime=0)
    text = io.TextIOWrapper(compressed, encoding="utf-8", newline="")
    return text, binary


def normalize_kline_archive(
    ref: ArchiveRef,
    archive_path: str | Path,
    output_path: str | Path,
    quality_path: str | Path,
    *,
    expected_sha256: str | None = None,
) -> QualityReport:
    if ref.kind not in {"kline", "reference_kline"}:
        raise DataContractError(f"normalizer does not support kind={ref.kind!r}")
    archive = Path(archive_path)
    if not archive.exists():
        raise FileNotFoundError(archive)
    source_hash = file_sha256(archive)
    if expected_sha256 and source_hash != expected_sha256:
        raise DataContractError(
            f"archive checksum changed: expected {expected_sha256}, got {source_hash}"
        )

    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    quality_destination = Path(quality_path)
    quality_destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    duration_us = interval_to_us(ref.interval)
    requested_start_us, requested_end_us = _utc_day_bounds(ref.period_start, ref.period_end)

    rows_read = 0
    rows_written = 0
    duplicates = 0
    gaps: list[Gap] = []
    missing_bars = 0
    canonicalization = CanonicalizationStats()
    first_open: int | None = None
    previous_open: int | None = None
    previous_fingerprint: tuple[str, ...] | None = None

    text, binary = _open_deterministic_gzip_text(temporary)
    try:
        writer = csv.DictWriter(text, fieldnames=KLINE_OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()

        def validate_source_row(row: list[str], source_line_number: int) -> None:
            _validate_ohlc(
                row,
                source_line_number,
                allow_negative=ref.dataset == "premiumIndexKlines",
            )
            if ref.kind == "kline":
                _validate_trade_fields(row, source_line_number)

        def canonical_rows() -> Iterator[list[str]]:
            try:
                yield from canonicalize_kline_rows(
                    _archive_rows(archive),
                    duration_us=duration_us,
                    kind=ref.kind,
                    timestamp_to_us=timestamp_to_us,
                    validate_row=validate_source_row,
                    stats=canonicalization,
                )
            except SourceCanonicalizationError as exc:
                raise DataContractError(str(exc)) from exc

        for line_number, raw in enumerate(canonical_rows(), start=1):
            rows_read += 1
            open_time_us = timestamp_to_us(raw[0])
            if not (requested_start_us <= open_time_us < requested_end_us):
                continue
            if open_time_us % duration_us != 0:
                raise DataContractError(
                    f"open time {open_time_us} is not aligned to {ref.interval} at row {line_number}"
                )
            source_close_us = timestamp_to_us(raw[6])
            close_exclusive_us = open_time_us + duration_us
            if not open_time_us <= source_close_us <= close_exclusive_us:
                raise DataContractError(
                    f"canonicalizer emitted an invalid close time at row {line_number}: "
                    f"open={open_time_us}, source_close={source_close_us}, "
                    f"close_exclusive={close_exclusive_us}"
                )
            _validate_ohlc(
                raw,
                line_number,
                allow_negative=ref.dataset == "premiumIndexKlines",
            )
            if ref.kind == "kline":
                _validate_trade_fields(raw, line_number)

            fingerprint = tuple(raw)
            if previous_open is not None:
                if open_time_us == previous_open:
                    if fingerprint == previous_fingerprint:
                        duplicates += 1
                        continue
                    raise DataContractError(
                        f"conflicting duplicate open time {open_time_us} at source row {line_number}"
                    )
                if open_time_us < previous_open:
                    raise DataContractError(
                        f"source rows are not monotonic at row {line_number}: "
                        f"{open_time_us} < {previous_open}"
                    )
                expected_next = previous_open + duration_us
                if open_time_us > expected_next:
                    count = (open_time_us - expected_next) // duration_us
                    gaps.append(
                        Gap(
                            after_open_time_us=previous_open,
                            before_open_time_us=open_time_us,
                            missing_bars=count,
                        )
                    )
                    missing_bars += count

            trade_values = ref.kind == "kline"
            writer.writerow(
                {
                    "exchange": ref.exchange,
                    "market_path": ref.market_path,
                    "dataset": ref.dataset,
                    "dataset_kind": ref.kind,
                    "symbol": ref.symbol,
                    "interval": ref.interval,
                    "open_time_us": open_time_us,
                    "close_time_exclusive_us": close_exclusive_us,
                    "available_time_us": close_exclusive_us,
                    "source_close_time_us": source_close_us,
                    "open": raw[1],
                    "high": raw[2],
                    "low": raw[3],
                    "close": raw[4],
                    "base_volume": raw[5] if trade_values else "",
                    "quote_volume": raw[7] if trade_values else "",
                    "trade_count": raw[8] if trade_values else "",
                    "taker_buy_base_volume": raw[9] if trade_values else "",
                    "taker_buy_quote_volume": raw[10] if trade_values else "",
                    "source_field_5": raw[5],
                    "source_field_7": raw[7],
                    "source_field_8": raw[8],
                    "source_field_9": raw[9],
                    "source_field_10": raw[10],
                    "source_field_11": raw[11],
                    "source_url": ref.url,
                    "source_sha256": source_hash,
                    "archive_id": ref.archive_id,
                    "pipeline_version": PIPELINE_VERSION,
                }
            )
            rows_written += 1
            first_open = open_time_us if first_open is None else first_open
            previous_open = open_time_us
            previous_fingerprint = fingerprint
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
    output_hash = file_sha256(destination)
    report = QualityReport(
        archive_id=ref.archive_id,
        dataset=ref.dataset,
        symbol=ref.symbol,
        interval=ref.interval,
        source_url=ref.url,
        source_sha256=source_hash,
        output_path=destination.as_posix(),
        output_sha256=output_hash,
        rows_read=canonicalization.source_rows_read,
        rows_written=rows_written,
        exact_duplicates_removed=(duplicates + canonicalization.exact_duplicates_removed),
        gap_count=len(gaps),
        missing_bar_count=missing_bars,
        first_open_time_us=first_open,
        last_open_time_us=previous_open,
        requested_start=ref.period_start,
        requested_end=ref.period_end,
        gaps=tuple(gaps),
        source_close_time_anomaly_count=(canonicalization.source_close_time_anomaly_count),
        source_close_time_max_early_us=(canonicalization.source_close_time_max_early_us),
        source_open_time_anomaly_count=(canonicalization.source_open_time_anomaly_count),
        source_open_time_max_late_us=(canonicalization.source_open_time_max_late_us),
        source_close_time_late_count=(canonicalization.source_close_time_late_count),
        source_close_time_max_late_us=(canonicalization.source_close_time_max_late_us),
        segmented_bar_count=canonicalization.segmented_bar_count,
        segmented_source_rows_merged=(canonicalization.segmented_source_rows_merged),
        quarantined_source_row_count=(canonicalization.quarantined_source_row_count),
        quarantined_canonical_bar_count=(canonicalization.quarantined_canonical_bar_count),
        anomaly_examples=tuple(canonicalization.anomaly_examples),
        status=(
            "valid_with_quarantine" if canonicalization.quarantined_canonical_bar_count else "valid"
        ),
    )
    payload = asdict(report)
    quality_temporary = quality_destination.with_suffix(quality_destination.suffix + ".tmp")
    quality_temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(quality_temporary, quality_destination)
    return report


def _read_download_report(path: str | Path) -> dict[str, DownloadResult]:
    results: dict[str, DownloadResult] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            result = DownloadResult(**payload)
            results[result.archive_id] = result
    return results


def normalize_manifest(
    manifest_path: str | Path,
    download_report_path: str | Path,
    raw_root: str | Path,
    silver_root: str | Path,
    quality_root: str | Path,
) -> list[QualityReport]:
    refs = {item.archive_id: item for item in read_manifest(manifest_path)}
    downloads = _read_download_report(download_report_path)
    reports: list[QualityReport] = []
    for archive_id in sorted(downloads):
        result = downloads[archive_id]
        ref = refs.get(archive_id)
        if ref is None or ref.kind not in {"kline", "reference_kline"}:
            continue
        if result.status not in {"downloaded_verified", "verified_existing"}:
            continue
        raw_path = Path(raw_root) / ref.relative_path
        relative = Path(ref.relative_path)
        output_relative = relative.with_suffix("").with_suffix(".csv.gz")
        quality_relative = relative.with_suffix("").with_suffix(".quality.json")
        try:
            report = normalize_kline_archive(
                ref,
                raw_path,
                Path(silver_root) / output_relative,
                Path(quality_root) / quality_relative,
                expected_sha256=result.expected_sha256,
            )
        except (DataContractError, SourceCanonicalizationError) as exc:
            raise DataContractError(
                f"{ref.dataset_name}/{ref.symbol}/{ref.period_start}: {exc}"
            ) from exc
        reports.append(report)
    return reports
