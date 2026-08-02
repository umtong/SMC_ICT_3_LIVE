from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import csv
import json
import os


CURRENT_FILE = "CURRENT"
METADATA_FILE = "PREPARED_DATA.json"
CATALOG_FILE = "catalog.csv"
ENV_ROOT = "SMC_ICT_PREPARED_DATA_ROOT"


@dataclass(frozen=True, slots=True)
class PreparedRelease:
    release_id: str
    root: Path
    silver_root: Path
    gold_root: Path
    quality_root: Path
    catalog_path: Path
    metadata_path: Path
    metadata: dict[str, object]

    def summary(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("metadata")
        return {
            **{key: value.as_posix() if isinstance(value, Path) else value for key, value in payload.items()},
            "status": self.metadata.get("status", "unknown"),
            "period_utc": self.metadata.get("period_utc"),
            "symbols": self.metadata.get("symbols", []),
            "timeframes": self.metadata.get("timeframes", []),
            "files": self.metadata.get("files", {}),
            "rows": self.metadata.get("rows", {}),
            "external_runtime_dependency": self.metadata.get("external_runtime_dependency"),
        }


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _find_repository_root() -> Path:
    starts = [Path.cwd().resolve(), Path(__file__).resolve()]
    visited: set[Path] = set()
    for start in starts:
        for candidate in (start, *start.parents):
            if candidate in visited:
                continue
            visited.add(candidate)
            if (candidate / "pyproject.toml").is_file() and (candidate / "data").is_dir():
                return candidate
    raise FileNotFoundError(
        "repository root not found; run inside the checkout or set "
        f"{ENV_ROOT} to data/prepared or a prepared release directory"
    )


def _resolve_release_root(root: str | Path | None = None) -> tuple[str, Path]:
    configured = root or os.environ.get(ENV_ROOT)
    base = Path(configured).expanduser().resolve() if configured else _find_repository_root() / "data" / "prepared"

    if (base / METADATA_FILE).is_file():
        metadata = json.loads((base / METADATA_FILE).read_text(encoding="utf-8"))
        release_id = str(metadata.get("release_id") or base.name)
        return release_id, base

    current = base / CURRENT_FILE
    if not current.is_file():
        raise FileNotFoundError(
            f"prepared research data is not installed at {base}; expected {current}"
        )
    release_id = current.read_text(encoding="utf-8").strip()
    if not release_id or release_id in {".", ".."} or "/" in release_id or "\\" in release_id:
        raise ValueError(f"invalid prepared release id in {current}: {release_id!r}")
    return release_id, base / release_id


def load_prepared_release(root: str | Path | None = None) -> PreparedRelease:
    release_id, release_root = _resolve_release_root(root)
    metadata_path = release_root / METADATA_FILE
    if not metadata_path.is_file():
        raise FileNotFoundError(f"prepared release metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("release_id") != release_id:
        raise ValueError(
            f"release id mismatch: CURRENT={release_id!r}, metadata={metadata.get('release_id')!r}"
        )
    paths = metadata.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"invalid paths contract in {metadata_path}")

    def required_path(name: str, default: str) -> Path:
        value = paths.get(name, default)
        if not isinstance(value, str) or not value:
            raise ValueError(f"invalid {name!r} path in {metadata_path}")
        candidate = (release_root / value).resolve()
        try:
            candidate.relative_to(release_root.resolve())
        except ValueError as exc:
            raise ValueError(f"prepared path escapes release root: {name}={value!r}") from exc
        return candidate

    prepared = PreparedRelease(
        release_id=release_id,
        root=release_root,
        silver_root=required_path("silver", "silver"),
        gold_root=required_path("gold", "gold"),
        quality_root=required_path("quality", "quality"),
        catalog_path=required_path("catalog", CATALOG_FILE),
        metadata_path=metadata_path,
        metadata=metadata,
    )
    for path in (prepared.silver_root, prepared.gold_root, prepared.quality_root):
        if not path.is_dir():
            raise FileNotFoundError(f"prepared data directory not found: {path}")
    if not prepared.catalog_path.is_file():
        raise FileNotFoundError(f"prepared catalog not found: {prepared.catalog_path}")
    return prepared


def verify_prepared_release(prepared: PreparedRelease) -> dict[str, object]:
    expected_catalog_hash = prepared.metadata.get("catalog_sha256")
    actual_catalog_hash = file_sha256(prepared.catalog_path)
    if expected_catalog_hash != actual_catalog_hash:
        raise ValueError(
            "prepared catalog checksum mismatch: "
            f"expected={expected_catalog_hash}, actual={actual_catalog_hash}"
        )

    checked = 0
    checked_bytes = 0
    with prepared.catalog_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"relative_path", "bytes", "sha256"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"prepared catalog missing columns: {sorted(required)}")
        for row in reader:
            relative = Path(row["relative_path"])
            candidate = (prepared.root / relative).resolve()
            try:
                candidate.relative_to(prepared.root.resolve())
            except ValueError as exc:
                raise ValueError(f"catalog path escapes release root: {relative}") from exc
            if not candidate.is_file():
                raise FileNotFoundError(f"cataloged prepared file not found: {candidate}")
            expected_size = int(row["bytes"])
            actual_size = candidate.stat().st_size
            if expected_size != actual_size:
                raise ValueError(
                    f"prepared file size mismatch: {relative}; expected={expected_size}, actual={actual_size}"
                )
            actual_hash = file_sha256(candidate)
            if actual_hash != row["sha256"]:
                raise ValueError(
                    f"prepared file checksum mismatch: {relative}; "
                    f"expected={row['sha256']}, actual={actual_hash}"
                )
            checked += 1
            checked_bytes += actual_size

    silver_files = len(list(prepared.silver_root.rglob("*.csv.gz")))
    gold_files = len(list(prepared.gold_root.rglob("*.csv.gz")))
    expected_files = prepared.metadata.get("files", {})
    if isinstance(expected_files, dict):
        for name, actual in (("silver", silver_files), ("gold", gold_files)):
            expected = expected_files.get(name)
            if expected is not None and int(expected) != actual:
                raise ValueError(
                    f"prepared {name} file count mismatch: expected={expected}, actual={actual}"
                )

    return {
        "status": "verified",
        "release_id": prepared.release_id,
        "root": prepared.root.as_posix(),
        "catalog_sha256": actual_catalog_hash,
        "cataloged_files_checked": checked,
        "cataloged_bytes_checked": checked_bytes,
        "silver_files": silver_files,
        "gold_files": gold_files,
    }
