from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import csv
import json
import os
import shutil
import time
import zipfile

from .catalog import CATALOG_COLUMNS
from .prepared import file_sha256, load_prepared_release, verify_prepared_release


DEFAULT_INDEX_URL = (
    "https://github.com/umtong/SMC_ICT_3_LIVE/releases/download/"
    "market-data-full-history-v1.0.0/full-history-v1.0.0.index.json"
)


@dataclass(frozen=True, slots=True)
class DistributionAsset:
    partition_id: str
    file: str
    url: str
    bytes: int
    sha256: str
    files: dict[str, int]
    rows: dict[str, int]


@dataclass(frozen=True, slots=True)
class DistributionIndex:
    release_id: str
    tag: str
    repository: str
    period_utc: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    source_datasets: tuple[str, ...]
    assets: tuple[DistributionAsset, ...]
    raw: dict[str, object]


def _read_json_source(source: str | Path) -> dict[str, object]:
    candidate = Path(source).expanduser() if not str(source).startswith(("http://", "https://")) else None
    if candidate is not None and candidate.is_file():
        return json.loads(candidate.read_text(encoding="utf-8"))

    url = str(source)
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"distribution index must be a local file or HTTPS URL: {source}")
    request = Request(url, headers={"User-Agent": "smc-ict-market-data/1.0"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - caller-selected HTTPS index
        return json.loads(response.read().decode("utf-8"))


def load_distribution_index(source: str | Path = DEFAULT_INDEX_URL) -> DistributionIndex:
    payload = _read_json_source(source)
    required = {
        "release_id",
        "tag",
        "repository",
        "period_utc",
        "symbols",
        "timeframes",
        "source_datasets",
        "assets",
    }
    missing = required - payload.keys()
    if missing:
        raise ValueError(f"distribution index missing fields: {sorted(missing)}")

    assets: list[DistributionAsset] = []
    seen_partitions: set[str] = set()
    for raw_asset in payload["assets"]:
        if not isinstance(raw_asset, dict):
            raise ValueError("distribution asset must be an object")
        asset = DistributionAsset(
            partition_id=str(raw_asset["partition_id"]),
            file=str(raw_asset["file"]),
            url=str(raw_asset["url"]),
            bytes=int(raw_asset["bytes"]),
            sha256=str(raw_asset["sha256"]),
            files={str(key): int(value) for key, value in dict(raw_asset["files"]).items()},
            rows={str(key): int(value) for key, value in dict(raw_asset["rows"]).items()},
        )
        if asset.partition_id in seen_partitions:
            raise ValueError(f"duplicate distribution partition: {asset.partition_id}")
        if len(asset.sha256) != 64:
            raise ValueError(f"invalid asset SHA-256 for {asset.file}")
        parsed = urlparse(asset.url)
        if parsed.scheme != "https" or parsed.netloc != "github.com":
            raise ValueError(f"asset URL must be an HTTPS github.com release URL: {asset.url}")
        seen_partitions.add(asset.partition_id)
        assets.append(asset)

    assets.sort(key=lambda item: item.partition_id)
    return DistributionIndex(
        release_id=str(payload["release_id"]),
        tag=str(payload["tag"]),
        repository=str(payload["repository"]),
        period_utc=str(payload["period_utc"]),
        symbols=tuple(str(value) for value in payload["symbols"]),
        timeframes=tuple(str(value) for value in payload["timeframes"]),
        source_datasets=tuple(str(value) for value in payload["source_datasets"]),
        assets=tuple(assets),
        raw=payload,
    )


def _download_asset(asset: DistributionAsset, cache_root: Path, retries: int = 4) -> Path:
    cache_root.mkdir(parents=True, exist_ok=True)
    destination = cache_root / asset.file
    if destination.is_file() and destination.stat().st_size == asset.bytes:
        if file_sha256(destination) == asset.sha256:
            return destination
        destination.unlink()

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        temporary: Path | None = None
        try:
            request = Request(asset.url, headers={"User-Agent": "smc-ict-market-data/1.0"})
            with urlopen(request, timeout=120) as response:  # noqa: S310 - validated GitHub release URL
                with NamedTemporaryFile(
                    mode="wb", dir=cache_root, prefix=f".{asset.file}.", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                    handle.flush()
                    os.fsync(handle.fileno())
            if temporary.stat().st_size != asset.bytes:
                raise ValueError(
                    f"asset size mismatch for {asset.file}: "
                    f"expected={asset.bytes}, actual={temporary.stat().st_size}"
                )
            actual_hash = file_sha256(temporary)
            if actual_hash != asset.sha256:
                raise ValueError(
                    f"asset checksum mismatch for {asset.file}: "
                    f"expected={asset.sha256}, actual={actual_hash}"
                )
            os.replace(temporary, destination)
            return destination
        except Exception as exc:
            last_error = exc
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(min(2**attempt, 8))
    assert last_error is not None
    raise last_error


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            target = (destination / member.filename).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"unsafe ZIP member path: {member.filename}") from exc
        handle.extractall(destination)


def _verify_partition(root: Path, expected_partition: str) -> tuple[list[dict[str, str]], dict[str, object]]:
    metadata_path = root / "PARTITION.json"
    catalog_path = root / "catalog.csv"
    if not metadata_path.is_file() or not catalog_path.is_file():
        raise ValueError(f"partition package lacks metadata/catalog: {root}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("partition_id") != expected_partition:
        raise ValueError(
            f"partition id mismatch: expected={expected_partition}, actual={metadata.get('partition_id')}"
        )
    if metadata.get("catalog_sha256") != file_sha256(catalog_path):
        raise ValueError(f"partition catalog checksum mismatch: {expected_partition}")

    rows: list[dict[str, str]] = []
    with catalog_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != CATALOG_COLUMNS:
            raise ValueError(f"unexpected partition catalog columns: {reader.fieldnames}")
        for row in reader:
            relative = Path(row["relative_path"])
            source = (root / relative).resolve()
            try:
                source.relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(f"partition catalog path escapes root: {relative}") from exc
            if not source.is_file():
                raise FileNotFoundError(f"partition file missing: {source}")
            if source.stat().st_size != int(row["bytes"]):
                raise ValueError(f"partition file size mismatch: {relative}")
            if file_sha256(source) != row["sha256"]:
                raise ValueError(f"partition file checksum mismatch: {relative}")
            rows.append(dict(row))
    return rows, metadata


def _copy_cataloged_files(
    source_root: Path,
    staging_root: Path,
    rows: list[dict[str, str]],
    seen_paths: set[str],
) -> None:
    for row in rows:
        relative = row["relative_path"]
        if relative in seen_paths:
            raise ValueError(f"duplicate path across distribution partitions: {relative}")
        seen_paths.add(relative)
        source = source_root / relative
        destination = staging_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def _catalog_record(path: Path, root: Path) -> dict[str, str | int]:
    return {
        "relative_path": path.relative_to(root).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": file_sha256(path),
        "format": path.suffix.lstrip("."),
        "rows": 0,
        "first_open_time_us": "",
        "last_open_time_us": "",
    }


def install_distribution(
    *,
    index_source: str | Path = DEFAULT_INDEX_URL,
    destination_base: str | Path = Path("data/installed"),
    cache_root: str | Path | None = None,
    partitions: set[str] | None = None,
    workers: int = 3,
    force: bool = False,
) -> dict[str, object]:
    index = load_distribution_index(index_source)
    selected = [asset for asset in index.assets if partitions is None or asset.partition_id in partitions]
    if not selected:
        raise ValueError("no distribution partitions selected")
    if partitions is not None:
        unknown = sorted(partitions - {asset.partition_id for asset in index.assets})
        if unknown:
            raise ValueError(f"unknown distribution partitions: {unknown}")

    suffix = "" if len(selected) == len(index.assets) else "__" + "-".join(
        asset.partition_id for asset in selected
    )
    installed_release_id = index.release_id + suffix
    base = Path(destination_base).expanduser().resolve()
    destination = base / installed_release_id
    if destination.exists() and not force:
        prepared = load_prepared_release(destination)
        verification = verify_prepared_release(prepared)
        return {**prepared.summary(), "status": "already_installed", "verification": verification}

    cache = (
        Path(cache_root).expanduser().resolve()
        if cache_root is not None
        else Path.home() / ".cache" / "smc-ict-market-data" / index.release_id
    )
    downloaded: dict[str, Path] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_download_asset, asset, cache): asset for asset in selected}
        for future in as_completed(futures):
            asset = futures[future]
            downloaded[asset.partition_id] = future.result()

    staging = base / f".{installed_release_id}.installing"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    all_rows: list[dict[str, str]] = []
    extra_records: list[dict[str, str | int]] = []
    seen_paths: set[str] = set()
    partition_metadata: list[dict[str, object]] = []

    try:
        for asset in selected:
            extraction = staging.parent / f".{installed_release_id}.{asset.partition_id}.extract"
            if extraction.exists():
                shutil.rmtree(extraction)
            _safe_extract(downloaded[asset.partition_id], extraction)
            rows, metadata = _verify_partition(extraction, asset.partition_id)
            _copy_cataloged_files(extraction, staging, rows, seen_paths)
            all_rows.extend(rows)
            partition_metadata.append(metadata)

            package_evidence = staging / "quality" / "packages" / asset.partition_id
            package_evidence.mkdir(parents=True, exist_ok=True)
            for name in ("PARTITION.json", "catalog.csv", "catalog.csv.metadata.json"):
                source = extraction / name
                if source.is_file():
                    target = package_evidence / name
                    shutil.copy2(source, target)
                    extra_records.append(_catalog_record(target, staging))
            shutil.rmtree(extraction)

        catalog = staging / "catalog.csv"
        with catalog.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CATALOG_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(sorted([*all_rows, *extra_records], key=lambda row: str(row["relative_path"])))

        totals = {
            "files": {
                "silver": sum(int(meta["files"]["silver"]) for meta in partition_metadata),
                "gold": sum(int(meta["files"]["gold"]) for meta in partition_metadata),
            },
            "rows": {
                "silver": sum(int(meta["rows"]["silver"]) for meta in partition_metadata),
                "gold": sum(int(meta["rows"]["gold"]) for meta in partition_metadata),
            },
        }
        metadata = {
            "schema_version": "1.0",
            "release_id": installed_release_id,
            "source_release_id": index.release_id,
            "status": "ready",
            "default": True,
            "period_utc": index.period_utc,
            "partitions": [asset.partition_id for asset in selected],
            "symbols": list(index.symbols),
            "source_datasets": list(index.source_datasets),
            "base_interval": "1m",
            "timeframes": list(index.timeframes),
            **totals,
            "paths": {
                "silver": "silver",
                "gold": "gold",
                "quality": "quality",
                "catalog": "catalog.csv",
            },
            "catalog_sha256": file_sha256(catalog),
            "distribution_tag": index.tag,
            "distribution_index": str(index_source),
            "external_runtime_dependency": False,
            "external_data_download_required": False,
        }
        (staging / "PREPARED_DATA.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if destination.exists():
            shutil.rmtree(destination)
        os.replace(staging, destination)
        base.mkdir(parents=True, exist_ok=True)
        (base / "CURRENT").write_text(installed_release_id + "\n", encoding="utf-8")
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    prepared = load_prepared_release(base)
    verification = verify_prepared_release(prepared)
    return {**prepared.summary(), "status": "installed", "verification": verification}
