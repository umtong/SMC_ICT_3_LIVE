from __future__ import annotations

from pathlib import Path
import csv
import gzip
import importlib.util
import sys

import pytest

from smc_ict_data.normalization import KLINE_OUTPUT_COLUMNS

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_partition.py"
SPEC = importlib.util.spec_from_file_location(
    "smc_ict_materialize_partition_test_module",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)
resample_partition = MODULE.resample_partition


START_US = 1_704_067_200_000_000


def write_silver(path: Path, *, symbol: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=KLINE_OUTPUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for index in range(10):
            open_time = START_US + index * 60_000_000
            writer.writerow(
                {
                    "exchange": "binance",
                    "market_path": "spot",
                    "dataset": "klines",
                    "dataset_kind": "kline",
                    "symbol": symbol,
                    "interval": "1m",
                    "open_time_us": open_time,
                    "close_time_exclusive_us": open_time + 60_000_000,
                    "available_time_us": open_time + 60_000_000,
                    "source_close_time_us": open_time + 59_999_000,
                    "open": str(100 + index),
                    "high": str(101 + index),
                    "low": str(99 + index),
                    "close": str(100.5 + index),
                    "base_volume": "1",
                    "quote_volume": "100",
                    "trade_count": "1",
                    "taker_buy_base_volume": "0.5",
                    "taker_buy_quote_volume": "50",
                    "source_field_5": "1",
                    "source_field_7": "100",
                    "source_field_8": "1",
                    "source_field_9": "0.5",
                    "source_field_10": "50",
                    "source_field_11": "0",
                    "source_url": "https://example.invalid/source.zip",
                    "source_sha256": "0" * 64,
                    "archive_id": f"test-{symbol}",
                    "pipeline_version": "test",
                }
            )


def test_parallel_partition_resampling_is_complete_and_deterministic(tmp_path: Path) -> None:
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    quality = tmp_path / "quality"
    for symbol in ("BTCUSDT", "ETHUSDT"):
        write_silver(
            silver
            / "binance"
            / "spot"
            / "klines"
            / symbol
            / "1m"
            / "2024"
            / "01"
            / f"{symbol}-1m-2024-01.csv.gz",
            symbol=symbol,
        )

    jobs = resample_partition(
        silver,
        gold,
        quality,
        workers=2,
        targets=("5m",),
    )

    assert jobs == 2
    outputs = sorted(gold.rglob("*.csv.gz"))
    reports = sorted(quality.rglob("*.quality.json"))
    assert len(outputs) == 2
    assert len(reports) == 2
    for output in outputs:
        with gzip.open(output, "rt", encoding="utf-8", newline="") as handle:
            assert len(list(csv.DictReader(handle))) == 2


def test_resampling_rejects_nonpositive_worker_count(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="workers must be positive"):
        resample_partition(
            tmp_path / "silver",
            tmp_path / "gold",
            tmp_path / "quality",
            workers=0,
            targets=("5m",),
        )
