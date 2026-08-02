from datetime import date
from pathlib import Path

import pytest

from smc_ict_data.archive import plan_archives
from smc_ict_data.model import load_config


CONFIG = Path(__file__).parents[1] / "configs" / "market_data.toml"


def test_golden_month_has_four_symbols_and_five_core_datasets() -> None:
    config = load_config(CONFIG)
    refs = plan_archives(
        config,
        date(2024, 1, 1),
        date(2024, 1, 31),
        date(2024, 2, 12),
    )
    assert len(refs) == 20
    assert {item.symbol for item in refs} == {"BTCUSDT", "ETHUSDT", "XRPUSDT", "SOLUSDT"}
    assert {item.period for item in refs} == {"monthly"}
    spot = next(
        item for item in refs if item.dataset_name == "spot_klines" and item.symbol == "BTCUSDT"
    )
    assert spot.url == (
        "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip"
    )
    mark = next(
        item
        for item in refs
        if item.dataset_name == "um_mark_price_klines" and item.symbol == "ETHUSDT"
    )
    assert mark.url == (
        "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/"
        "ETHUSDT/1m/ETHUSDT-1m-2024-01.zip"
    )
    assert mark.checksum_url.endswith(".zip.CHECKSUM")


def test_unpublished_month_uses_daily_candidates() -> None:
    config = load_config(CONFIG)
    refs = plan_archives(
        config,
        date(2026, 7, 1),
        date(2026, 7, 31),
        date(2026, 8, 2),
    )
    assert len(refs) == 31 * 4 * 5
    assert {item.period for item in refs} == {"daily"}


def test_incomplete_utc_day_is_rejected() -> None:
    config = load_config(CONFIG)
    with pytest.raises(ValueError, match="incomplete UTC days"):
        plan_archives(config, date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 2))
