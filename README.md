# SMC / ICT 3 — 바로 사용할 수 있는 암호자산 시장 데이터 기반

이 저장소는 BTC, ETH, XRP, SOL 데이트레이딩 연구에 필요한 **검증된 시장 데이터와 이를 해석하는 데이터 계약·코드·테스트를 함께 제공**합니다.

> 연구자는 GitHub `main`을 단일 진입점으로 사용하십시오. Google Drive를 찾거나 Binance 원천 파일을 직접 수집하지 않고, 이미 준비된 데이터로 시나리오 논리 연구를 시작할 수 있습니다.

## 두 단계의 준비 데이터

### 1. 복제 즉시 포함되는 골든 기준셋

`main`에는 `golden-2024-01-v1.0.0`이 실제 파일로 커밋되어 있습니다. 코드·데이터 계약·연구 아이디어를 즉시 실행하고 검증하는 기준셋입니다.

```bash
PYTHONPATH=src python3 -m smc_ict_data.cli ready --verify
```

이 명령은 네트워크를 사용하지 않습니다.

### 2. 전체 연구 이력

2017-01-01부터 2026-07-31까지의 전체 이력은 공식 원천에서 매번 받는 방식이 아니라, 프로젝트가 미리 검증·정규화·재표본화한 **연도별 GitHub Release 자산**으로 제공합니다.

```bash
make setup-full
```

또는 직접 실행합니다.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/smc-data install
.venv/bin/smc-data ready --verify
```

`smc-data install`은 다음만 수행합니다.

1. 프로젝트 GitHub Release의 고정 인덱스를 읽음
2. 미리 제작된 연도별 ZIP을 내려받음
3. 각 ZIP의 크기와 SHA-256 검증
4. 압축 내부 카탈로그의 모든 파일 크기와 SHA-256 검증
5. `data/installed/full-history-v1.0.0`에 원자적으로 설치
6. 통합 카탈로그를 만들고 다시 전체 검증

Google Drive나 거래소 데이터 서버는 사용하지 않습니다. 설치가 끝나면 `smc-data ready`와 Python 로더는 `data/installed`의 전체 이력을 자동으로 우선 선택합니다.

필요한 연도만 설치할 수도 있습니다.

```bash
smc-data install --year 2022 --year 2023 --year 2024
```

배포 자산과 크기·행 수를 설치 전에 확인합니다.

```bash
smc-data distribution
```

## 포함된 데이터 계층

| 시장 | 데이터셋 | 기준 간격 | 용도 |
|---|---|---:|---|
| Binance Spot | `klines` | 1m | 현물 거래가격 |
| Binance USD-M | `klines` | 1m | 무기한 선물 거래가격 |
| Binance USD-M | `markPriceKlines` | 1m | 증거금·청산 기준 가격 |
| Binance USD-M | `indexPriceKlines` | 1m | 현물 바스켓 기반 지수가격 |
| Binance USD-M | `premiumIndexKlines` | 1m | 선물-지수 괴리, 음수 허용 |

모든 검증된 1분 Silver 파일에서 다음 Gold 시간봉을 미리 파생합니다.

```text
5m / 15m / 1h / 4h
```

서로 다른 의미의 가격을 하나의 모호한 `close`로 합치지 않습니다. 연구자는 거래가·mark·index·premium 중 어떤 값을 사용했는지 명시해야 합니다.

## 복제 즉시 포함된 골든 기준셋

```text
data/prepared/
├── CURRENT
└── golden-2024-01-v1.0.0/
    ├── PREPARED_DATA.json
    ├── catalog.csv
    ├── silver/
    ├── gold/
    └── quality/
```

| 항목 | 값 |
|---|---:|
| 기간 | `[2024-01-01, 2024-02-01)` UTC |
| 심볼 | BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT |
| 1분 Silver | 20파일 / 892,800행 |
| Gold | 80파일 / 256,680행 |
| 정확 중복 | 0 |
| 결측 1분 봉 | 0 |
| 불완전 Gold 버킷 | 0 |

이는 전체 연구 기간을 대신하는 샘플이 아니라, 코드와 계약을 네트워크 없이 즉시 검사하는 불변 기준 릴리스입니다.

## 전체 이력 설치 구조

```text
data/installed/
├── CURRENT
└── full-history-v1.0.0/
    ├── PREPARED_DATA.json
    ├── catalog.csv
    ├── silver/
    │   └── binance/{spot,futures/...}/.../1m/{year}/{month}/*.csv.gz
    ├── gold/
    │   └── binance/{spot,futures/...}/.../{5m,15m,1h,4h}/{year}/{month}/*.csv.gz
    └── quality/
        ├── partitions/
        └── packages/
```

설치 파일은 Git에 다시 커밋하지 않으며, 동일한 Release 인덱스와 SHA-256으로 어느 연구 환경에서도 재현합니다.

## Python에서 현재 데이터 사용

```python
from smc_ict_data.prepared import load_prepared_release

release = load_prepared_release()
print(release.release_id)
print(release.silver_root)
print(release.gold_root)
```

`data/installed/CURRENT`가 있으면 전체 이력을, 없으면 저장소 내장 골든 기준셋을 반환합니다. 특정 릴리스를 명시하려면 경로를 전달합니다.

```python
release = load_prepared_release("data/prepared")
```

외부 패키지 없이 CSV.gz를 읽을 수 있습니다.

```python
import csv
import gzip
from smc_ict_data.prepared import load_prepared_release

release = load_prepared_release()
path = next(release.silver_root.rglob("BTCUSDT-1m-2024-01.csv.gz"))

with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
    first_bar = next(csv.DictReader(handle))
    print(first_bar)
```

## 가장 중요한 시간 계약

모든 정규화 타임스탬프는 UTC Unix microseconds(`int64`)입니다.

- 봉 구간: `[open_time_us, close_time_exclusive_us)`
- 봉 전체를 사용할 수 있는 최초 시점: `available_time_us = close_time_exclusive_us`
- Binance 원본 close time: `source_close_time_us`에 보존
- 2025-01-01 이후 Spot 원본의 microsecond 전환 자동 감지
- 결측 봉: 보고하되 가격으로 채우지 않음
- 정확 중복: 감사 수량을 남기고 제거
- 충돌 중복: 계약 위반으로 거부
- 상위 시간봉: 필요한 모든 1분 봉이 있을 때만 생성

자세한 내용은 [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md)와 [`docs/BACKTEST_SEMANTICS.md`](docs/BACKTEST_SEMANTICS.md)를 참조하십시오.

## 연구 경계

Silver에는 관측 가능한 원천 사실과 시간 의미만 들어 있습니다. 다음 판단을 미리 라벨링하지 않습니다.

```text
BOS / CHoCH / displacement / liquidity sweep / FVG / order block
premium-discount / dealing range / session bias / signal / outcome
```

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

## GitHub와 Drive의 역할

### GitHub `main`과 GitHub Releases

연구의 전체 진입점입니다.

- 코드·스키마·테스트·문서
- 복제 즉시 실행 가능한 골든 기준 데이터
- 전체 이력의 사전 제작 연도별 Release 자산
- 설치 인덱스와 다단계 SHA-256 검증
- 새 릴리스 제작과 원천 감사 워크플로

### Google Drive

선택적 장기 보관·백업 장소일 뿐입니다. 연구 실행, 데이터 위치 확인, 전체 이력 설치에 필요하지 않습니다. 프로젝트 보관 경계도 `Project/SMC_ICT_3_LIVE`로 한정합니다.

## 외부 원천 재수집은 연구 절차가 아닙니다

`smc-data plan`, `download`, `build`는 데이터 릴리스 제작자만 다음 경우에 사용합니다.

- 새 기간을 정식 릴리스로 추가
- 공급자의 과거 파일 변경 감사
- 데이터 계약 변경 후 원천 재현성 검사

일반 연구자는 `smc-data install`로 이미 제작된 GitHub 자산을 설치한 뒤 시나리오 연구에 집중합니다.

## 주요 명령

```bash
smc-data distribution       # 전체 이력 배포 인덱스 확인
smc-data install            # 전체 이력 설치
smc-data install --year 2024
smc-data ready              # 현재 활성 릴리스 경로·요약
smc-data ready --verify     # 모든 설치 파일 검증
smc-data doctor             # 코드·설정·데이터 상태
make test                   # 단위·계약 테스트
```

운영·릴리스 절차는 [`docs/OPERATIONS.md`](docs/OPERATIONS.md), 데이터 아키텍처는 [`docs/DATA_ARCHITECTURE.md`](docs/DATA_ARCHITECTURE.md), 연구자의 사용 원칙은 [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md)에 있습니다.
