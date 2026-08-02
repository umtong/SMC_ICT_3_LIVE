# SMC / ICT 3 — 바로 사용할 수 있는 암호자산 시장 데이터 기반

이 저장소는 BTC, ETH, XRP, SOL 데이트레이딩 연구에 필요한 **검증된 시장 데이터와 이를 해석하는 데이터 계약·코드·테스트를 함께 제공**합니다.

> 연구자는 `main`을 복제한 뒤 `data/prepared/CURRENT`가 가리키는 릴리스를 바로 사용하십시오. 기본 연구를 시작하기 위해 Google Drive를 찾거나 Binance에서 데이터를 다시 수집할 필요가 없습니다.

## 즉시 사용

저장소 안의 데이터 위치와 상태를 확인합니다. 이 명령은 네트워크를 사용하지 않습니다.

```bash
PYTHONPATH=src python3 -m smc_ict_data.cli ready --verify
```

일반적인 개발 환경을 한 번에 구성하려면 다음을 실행합니다.

```bash
make setup
```

`make setup`은 로컬 가상환경에 이 저장소의 코드를 설치하고, 이미 Git에 포함된 연구 데이터를 검증합니다. 시장 데이터를 외부에서 내려받지 않습니다.

Python에서는 다음과 같이 현재 릴리스 경로를 얻습니다.

```python
from smc_ict_data.prepared import load_prepared_release

release = load_prepared_release()
print(release.release_id)
print(release.silver_root)
print(release.gold_root)
```

## Git에 준비된 기본 릴리스

현재 기본 릴리스는 다음과 같습니다.

```text
golden-2024-01-v1.0.0
```

범위와 구성:

| 항목 | 값 |
|---|---:|
| 기간 | `[2024-01-01, 2024-02-01)` UTC |
| 심볼 | BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT |
| 1분 Silver 파일 | 20개 |
| 1분 Silver 레코드 | 892,800개 |
| Gold 시간봉 | 5m, 15m, 1h, 4h |
| Gold 파일 | 80개 |
| Gold 레코드 | 256,680개 |
| 정확 중복 | 0개 |
| 결측 1분 봉 | 0개 |
| 불완전 Gold 버킷 | 0개 |

데이터는 저장소 안에 다음 구조로 들어 있습니다.

```text
data/prepared/
├── CURRENT
├── README.md
└── golden-2024-01-v1.0.0/
    ├── PREPARED_DATA.json
    ├── catalog.csv
    ├── silver/
    │   └── binance/{spot,futures/...}/.../*.csv.gz
    ├── gold/
    │   └── binance/{spot,futures/...}/.../{5m,15m,1h,4h}/.../*.csv.gz
    └── quality/
        ├── source/
        └── resample/
```

각 파일의 크기와 SHA-256은 `catalog.csv`에 고정되어 있습니다. `smc-data ready --verify`는 카탈로그 자체의 해시와 카탈로그에 기록된 모든 파일을 검증합니다.

## 제공하는 가격 계층

| 시장 | 데이터셋 | 기준 간격 | 용도 |
|---|---|---:|---|
| Binance Spot | `klines` | 1m | 현물 거래가격 |
| Binance USD-M | `klines` | 1m | 무기한 선물 거래가격 |
| Binance USD-M | `markPriceKlines` | 1m | 증거금·청산 기준 가격 |
| Binance USD-M | `indexPriceKlines` | 1m | 현물 바스켓 기반 지수가격 |
| Binance USD-M | `premiumIndexKlines` | 1m | 선물-지수 괴리, 음수 허용 |

서로 다른 의미의 가격을 하나의 모호한 `close`로 합치지 않습니다. 연구자는 시나리오에서 거래가·mark·index·premium 중 어떤 값을 사용했는지 명시해야 합니다.

## 가장 중요한 시간 계약

모든 정규화 타임스탬프는 UTC Unix microseconds(`int64`)입니다.

- 봉 구간: `[open_time_us, close_time_exclusive_us)`
- 봉 전체를 전략이 사용할 수 있는 최초 시점: `available_time_us = close_time_exclusive_us`
- Binance 원본 close time: `source_close_time_us`에 보존
- 2025-01-01 이후 Spot 원본의 microsecond 전환 자동 감지
- 결측 봉: 보고하되 가격으로 채우지 않음
- 정확 중복: 감사 수량을 남기고 제거
- 충돌 중복: 계약 위반으로 거부
- 상위 시간봉: 필요한 모든 1분 봉이 있을 때만 생성

자세한 내용은 [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md)와 [`docs/BACKTEST_SEMANTICS.md`](docs/BACKTEST_SEMANTICS.md)를 참조하십시오.

## 연구 경계

Silver에는 관측 가능한 원천 사실과 시간 의미만 들어 있습니다. 다음 SMC/ICT 판단을 미리 라벨링하지 않습니다.

```text
BOS / CHoCH / displacement / liquidity sweep / FVG / order block
premium-discount / dealing range / session bias / signal / outcome
```

패턴 검출기와 시나리오 상태 머신은 준비된 데이터 릴리스를 입력으로 받는 별도 연구 계층이어야 합니다.

```text
Prepared Market Data
        ↓
시장 구조·유동성 이벤트 검출
        ↓
시장 상태·세션·레짐 분류
        ↓
SMC/ICT 시나리오 상태 머신
        ↓
진입·무효화·청산 결정
        ↓
백테스트·실거래 공통 인터페이스
```

## 파일을 직접 읽는 예

외부 패키지 없이 CSV.gz를 읽을 수 있습니다.

```python
import csv
import gzip
from smc_ict_data.prepared import load_prepared_release

release = load_prepared_release()
path = next(release.silver_root.rglob("BTCUSDT-1m-2024-01.csv.gz"))

with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
    reader = csv.DictReader(handle)
    first_bar = next(reader)
    print(first_bar)
```

DuckDB를 사용하는 연구자는 선택적으로 설치한 뒤 전체 파티션을 직접 조회할 수 있습니다.

```bash
pip install -e .[analytics]
```

```sql
SELECT symbol, interval, min(open_time_us), max(open_time_us), count(*)
FROM read_csv_auto('data/prepared/golden-2024-01-v1.0.0/silver/**/*.csv.gz',
                   hive_partitioning = false)
GROUP BY symbol, interval;
```

## 코드와 데이터의 역할

### GitHub `main`

연구의 단일 진입점입니다.

- 즉시 사용할 수 있는 검증된 Silver·Gold 데이터
- 현재 릴리스 포인터와 해시 카탈로그
- 데이터 계약과 스키마
- 데이터 로더와 검증 명령
- 시나리오 연구에서 사용할 공통 코드
- 테스트와 CI
- 새 릴리스를 제작하는 수집·정규화·재표본화 도구

### Google Drive

장기 보관과 외부 백업을 위한 선택적 저장소입니다. 연구 실행에는 필요하지 않으며, 저장소 코드가 Drive 마운트나 다른 Drive 폴더를 요구하지 않습니다. 공식 프로젝트 보관 경계는 `Project/SMC_ICT_3_LIVE`뿐입니다.

## 외부 원천 재수집은 기본 연구 절차가 아닙니다

`smc-data plan`, `download`, `build`는 다음 경우에만 사용합니다.

- 새로운 기간을 데이터 릴리스로 추가할 때
- 공급자의 과거 파일 변경 여부를 감사할 때
- 데이터 계약이나 정규화 코드를 변경한 뒤 재현성을 검증할 때

일반 연구자는 이 과정을 반복하지 않고 Git에 준비된 릴리스를 사용합니다. 공식 원천 재현 감사도 모든 PR에서 실행하지 않으며, 명시적으로 시작하는 `audit-golden-source-reproducibility` 워크플로로 분리되어 있습니다.

## 주요 명령

```bash
# 준비된 데이터 위치와 요약
smc-data ready

# 준비된 모든 파일의 크기와 SHA-256 검증
smc-data ready --verify

# 코드·설정·준비 데이터 상태 확인
smc-data doctor

# 단위·계약 테스트
make test

# 새 데이터 릴리스 제작자용 원천 계획
smc-data plan --start YYYY-MM-DD --end YYYY-MM-DD --out manifest.csv
```

운영·릴리스 절차는 [`docs/OPERATIONS.md`](docs/OPERATIONS.md), 데이터 아키텍처는 [`docs/DATA_ARCHITECTURE.md`](docs/DATA_ARCHITECTURE.md), 연구자의 사용 원칙은 [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md)에 있습니다.
