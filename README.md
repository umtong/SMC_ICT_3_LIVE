# SMC / ICT 3 — Reproducible Crypto Market Data Foundation

This repository contains the reproducible market-data foundation for BTC, ETH, XRP and SOL day-trading research. Git stores code, schemas, tests and manifests; bulk immutable data is stored in the project Google Drive.

The canonical base layer is Binance Spot and USD-M Futures 1-minute public archive data. Higher timeframes are derived deterministically. Missing bars are reported, never price-filled.

## Golden snapshot source links

The first immutable contract-test snapshot is January 2024. These links are intentionally recorded as provenance:

- https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
- https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2024-01.zip
- https://data.binance.vision/data/spot/monthly/klines/XRPUSDT/1m/XRPUSDT-1m-2024-01.zip
- https://data.binance.vision/data/spot/monthly/klines/SOLUSDT/1m/SOLUSDT-1m-2024-01.zip
- https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
- https://data.binance.vision/data/futures/um/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2024-01.zip
- https://data.binance.vision/data/futures/um/monthly/klines/XRPUSDT/1m/XRPUSDT-1m-2024-01.zip
- https://data.binance.vision/data/futures/um/monthly/klines/SOLUSDT/1m/SOLUSDT-1m-2024-01.zip

Every archive has a companion `.CHECKSUM` object at the same URL with `.CHECKSUM` appended.

> Status: repository initialization. The complete pipeline, schemas, validation suite, catalog and Drive layout are added in the next atomic commit.
