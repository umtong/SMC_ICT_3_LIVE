from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import csv
import json
import os
import time

from .model import DatasetSpec, ProjectConfig


MANIFEST_COLUMNS = (
    "archive_id",
    "exchange",
    "market_path",
    "dataset_name",
    "dataset",
    "kind",
    "symbol",
    "interval",
    "period",
    "period_start",
    "period_end",
    "url",
    "checksum_url",
    "relative_path",
    "plan_status",
)


@dataclass(frozen=True, slots=True)
class ArchiveRef:
    archive_id: str
    exchange: str
    market_path: str
    dataset_name: str
    dataset: str
    kind: str
    symbol: str
    interval: str
    period: str
    period_start: str
    period_end: str
    url: str
    checksum_url: str
    relative_path: str
    plan_status: str = "candidate_unverified"

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ArchiveRef":
        return cls(**{name: row[name] for name in MANIFEST_COLUMNS})


@dataclass(frozen=True, slots=True)
class DownloadResult:
    archive_id: str
    status: str
    relative_path: str
    expected_sha256: str | None = None
    actual_sha256: str | None = None
    bytes: int | None = None
    error: str | None = None
    completed_at_utc: str | None = None


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _next_month(day: date) -> date:
    return date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1)


def _month_end(day: date) -> date:
    return _next_month(_month_start(day)) - timedelta(days=1)


def _iter_months(start: date, end: date) -> Iterator[date]:
    cursor = _month_start(start)
    last = _month_start(end)
    while cursor <= last:
        yield cursor
        cursor = _next_month(cursor)


def _first_monday_after(month: date) -> date:
    first_of_next = _next_month(month)
    return first_of_next + timedelta(days=(7 - first_of_next.weekday()) % 7)


def _monthly_is_published(month: date, as_of: date) -> bool:
    return _first_monday_after(month) <= as_of


def _archive_filename(spec: DatasetSpec, symbol: str, interval: str, label: str) -> str:
    if spec.is_interval_data:
        return f"{symbol}-{interval}-{label}.zip"
    return f"{symbol}-{spec.dataset}-{label}.zip"


def _archive_url(
    base_url: str,
    spec: DatasetSpec,
    symbol: str,
    interval: str,
    period: str,
    label: str,
) -> tuple[str, str]:
    parts = [base_url, "data", spec.market_path, period, spec.dataset, symbol]
    if spec.is_interval_data:
        parts.append(interval)
    filename = _archive_filename(spec, symbol, interval, label)
    parts.append(filename)
    url = "/".join(part.strip("/") for part in parts)
    return url, filename


def _make_ref(
    config: ProjectConfig,
    spec: DatasetSpec,
    symbol: str,
    interval: str,
    period: str,
    period_start: date,
    period_end: date,
    label: str,
) -> ArchiveRef:
    url, filename = _archive_url(config.source_base_url, spec, symbol, interval, period, label)
    relative = Path(
        config.exchange,
        spec.market_path,
        spec.dataset,
        symbol,
        interval if spec.is_interval_data else "events",
        str(period_start.year),
        f"{period_start.month:02d}",
        filename,
    ).as_posix()
    identity = "|".join(
        [config.exchange, spec.market_path, spec.dataset, symbol, interval, period, label]
    )
    archive_id = sha256(identity.encode("utf-8")).hexdigest()[:20]
    return ArchiveRef(
        archive_id=archive_id,
        exchange=config.exchange,
        market_path=spec.market_path,
        dataset_name=spec.name,
        dataset=spec.dataset,
        kind=spec.kind,
        symbol=symbol,
        interval=interval if spec.is_interval_data else "",
        period=period,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
        url=url,
        checksum_url=f"{url}.CHECKSUM",
        relative_path=relative,
    )


def plan_archives(
    config: ProjectConfig,
    start: date,
    end: date,
    as_of: date,
    *,
    include_disabled: bool = False,
) -> list[ArchiveRef]:
    """Create deterministic candidate URLs without pretending every symbol existed."""

    if start > end:
        raise ValueError("start must not be after end")
    if end >= as_of:
        raise ValueError("end must be earlier than as_of; incomplete UTC days are forbidden")

    specs = config.datasets if include_disabled else config.enabled_datasets
    refs: list[ArchiveRef] = []
    for spec in specs:
        for symbol in config.symbols:
            interval = config.base_interval
            for month in _iter_months(start, end):
                month_start = month
                month_end = _month_end(month)
                requested_start = max(start, month_start)
                requested_end = min(end, month_end)
                if _monthly_is_published(month, as_of):
                    label = f"{month.year:04d}-{month.month:02d}"
                    refs.append(
                        _make_ref(
                            config,
                            spec,
                            symbol,
                            interval,
                            "monthly",
                            requested_start,
                            requested_end,
                            label,
                        )
                    )
                else:
                    cursor = requested_start
                    while cursor <= requested_end:
                        label = cursor.isoformat()
                        refs.append(
                            _make_ref(
                                config,
                                spec,
                                symbol,
                                interval,
                                "daily",
                                cursor,
                                cursor,
                                label,
                            )
                        )
                        cursor += timedelta(days=1)
    refs.sort(key=lambda item: (item.dataset_name, item.symbol, item.period_start, item.url))
    return refs


def write_manifest(refs: Iterable[ArchiveRef], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for item in refs:
            writer.writerow(asdict(item))
    os.replace(temporary, destination)
    return destination


def read_manifest(path: str | Path) -> list[ArchiveRef]:
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = set(MANIFEST_COLUMNS) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"manifest missing columns: {sorted(missing)}")
        return [ArchiveRef.from_row(row) for row in reader]


def file_sha256(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch_to_path(url: str, destination: Path, retries: int, timeout: float) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "smc-ict-market-data/1.0"})
            with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed HTTPS manifest
                with NamedTemporaryFile(
                    mode="wb", dir=destination.parent, prefix=f".{destination.name}.", delete=False
                ) as temporary:
                    temporary_path = Path(temporary.name)
                    while chunk := response.read(1024 * 1024):
                        temporary.write(chunk)
                    temporary.flush()
                    os.fsync(temporary.fileno())
            os.replace(temporary_path, destination)
            return
        except HTTPError as exc:
            if exc.code == 404:
                raise
            last_error = exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
        if attempt < retries:
            time.sleep(min(2**attempt, 8))
    assert last_error is not None
    raise last_error


def _parse_checksum(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    token = text.split()[0] if text else ""
    if len(token) != 64 or any(char not in "0123456789abcdefABCDEF" for char in token):
        raise ValueError(f"invalid SHA-256 checksum payload in {path}")
    return token.lower()


def download_one(
    ref: ArchiveRef,
    raw_root: str | Path,
    *,
    retries: int = 4,
    timeout: float = 60.0,
) -> DownloadResult:
    destination = Path(raw_root) / ref.relative_path
    checksum_path = destination.with_name(destination.name + ".CHECKSUM")
    completed = datetime.now(timezone.utc).isoformat()
    try:
        if not checksum_path.exists():
            _fetch_to_path(ref.checksum_url, checksum_path, retries, timeout)
        expected = _parse_checksum(checksum_path)

        if destination.exists() and file_sha256(destination) == expected:
            return DownloadResult(
                archive_id=ref.archive_id,
                status="verified_existing",
                relative_path=ref.relative_path,
                expected_sha256=expected,
                actual_sha256=expected,
                bytes=destination.stat().st_size,
                completed_at_utc=completed,
            )

        _fetch_to_path(ref.url, destination, retries, timeout)
        actual = file_sha256(destination)
        if actual != expected:
            quarantine = destination.with_name(
                destination.name + f".checksum_mismatch.{actual[:12]}"
            )
            os.replace(destination, quarantine)
            return DownloadResult(
                archive_id=ref.archive_id,
                status="quarantined_checksum_mismatch",
                relative_path=ref.relative_path,
                expected_sha256=expected,
                actual_sha256=actual,
                bytes=quarantine.stat().st_size,
                error=f"moved to {quarantine.name}",
                completed_at_utc=completed,
            )
        return DownloadResult(
            archive_id=ref.archive_id,
            status="downloaded_verified",
            relative_path=ref.relative_path,
            expected_sha256=expected,
            actual_sha256=actual,
            bytes=destination.stat().st_size,
            completed_at_utc=completed,
        )
    except HTTPError as exc:
        status = "source_unavailable" if exc.code == 404 else "failed_http"
        return DownloadResult(
            archive_id=ref.archive_id,
            status=status,
            relative_path=ref.relative_path,
            error=f"HTTP {exc.code}: {exc.reason}",
            completed_at_utc=completed,
        )
    except Exception as exc:  # boundary: report each archive, continue the release
        return DownloadResult(
            archive_id=ref.archive_id,
            status="failed",
            relative_path=ref.relative_path,
            error=f"{type(exc).__name__}: {exc}",
            completed_at_utc=completed,
        )


def download_manifest(
    manifest_path: str | Path,
    raw_root: str | Path,
    report_path: str | Path,
    *,
    workers: int = 4,
    retries: int = 4,
    timeout: float = 60.0,
) -> list[DownloadResult]:
    refs = read_manifest(manifest_path)
    results: list[DownloadResult] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {
            pool.submit(download_one, ref, raw_root, retries=retries, timeout=timeout): ref
            for ref in refs
        }
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item.archive_id)

    destination = Path(report_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True) + "\n")
    os.replace(temporary, destination)
    return results
