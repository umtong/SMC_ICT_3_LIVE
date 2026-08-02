from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import tomllib


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    """One source dataset; market_path mirrors Binance Vision's URL hierarchy."""

    name: str
    market_path: str
    dataset: str
    kind: str
    download: bool = True
    normalize: bool = True

    @property
    def is_interval_data(self) -> bool:
        return self.kind in {"kline", "reference_kline"}


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    version: str
    exchange: str
    symbols: tuple[str, ...]
    base_interval: str
    history_start: date
    history_end: str
    source_base_url: str
    datasets: tuple[DatasetSpec, ...]

    @property
    def enabled_datasets(self) -> tuple[DatasetSpec, ...]:
        return tuple(item for item in self.datasets if item.download)


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"expected YYYY-MM-DD, got {value!r}") from exc


def latest_complete_utc_day(now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return current.astimezone(timezone.utc).date() - timedelta(days=1)


def resolve_history_end(value: str, now: datetime | None = None) -> date:
    if value == "latest_complete_day":
        return latest_complete_utc_day(now)
    return parse_date(value)


def load_config(path: str | Path) -> ProjectConfig:
    config_path = Path(path)
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    datasets = tuple(
        DatasetSpec(
            name=str(item["name"]),
            market_path=str(item["market_path"]).strip("/"),
            dataset=str(item["dataset"]),
            kind=str(item["kind"]),
            download=bool(item.get("download", True)),
            normalize=bool(item.get("normalize", True)),
        )
        for item in raw["datasets"]
    )
    symbols = tuple(str(item).upper() for item in raw["symbols"])
    if len(set(symbols)) != len(symbols):
        raise ValueError("symbols must be unique")
    if not symbols:
        raise ValueError("at least one symbol is required")

    return ProjectConfig(
        version=str(raw["version"]),
        exchange=str(raw["exchange"]),
        symbols=symbols,
        base_interval=str(raw["base_interval"]),
        history_start=parse_date(str(raw["history_start"])),
        history_end=str(raw["history_end"]),
        source_base_url=str(raw["source_base_url"]).rstrip("/"),
        datasets=datasets,
    )
