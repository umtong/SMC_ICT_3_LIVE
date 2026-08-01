# SMC / ICT 3 — 재현 가능한 암호자산 시장 데이터 기반

이 저장소는 BTC, ETH, XRP, SOL 데이트레이딩 연구를 위한 **시장 데이터 계약, 수집기, 검증기, 재표본화기, 품질 리포트와 배포 매니페스트**를 제공합니다. GitHub에는 코드·스키마·테스트·작은 매니페스트만 두고, 대용량 원본과 정규화 데이터는 프로젝트 Google Drive에 둡니다.

이 기반의 목표는 백테스트 수익률을 높여 보이는 데이터셋을 만드는 것이 아닙니다. 거래소 원본의 의미와 결함을 보존하면서, SMC/ICT 시나리오 연구가 동일한 입력을 재현하고 미래정보·암묵적 보간·타임스탬프 단위 혼용을 피하도록 하는 것입니다.

## 현재 제공 범위

| 계층 | 데이터 | 기준 간격 | 상태 |
|---|---|---:|---|
| Spot | Binance `klines` | 1m | 기본 활성화 |
| USD-M perpetual | 거래가 `klines` | 1m | 기본 활성화 |
| USD-M perpetual | `markPriceKlines` | 1m | 기본 활성화 |
| USD-M perpetual | `indexPriceKlines` | 1m | 기본 활성화 |
| USD-M perpetual | `premiumIndexKlines` | 1m | 기본 활성화 |
| Spot / USD-M | `aggTrades` | event | 선택적·기본 비활성화 |

대상 심볼은 `BTCUSDT`, `ETHUSDT`, `XRPUSDT`, `SOLUSDT`입니다. 5m, 15m, 1h, 4h 등은 1m Silver에서 결정적으로 파생합니다. 원천별로 서로 다른 의미를 가진 필드는 억지로 합치지 않습니다. 특히 mark/index/premium 봉의 보조 필드는 거래량이나 거래 건수로 노출하지 않습니다.

## 가장 중요한 시간 규칙

모든 정규화 타임스탬프는 UTC Unix microseconds(`int64`)입니다.

- 봉 구간: `[open_time_us, close_time_exclusive_us)`
- 전략이 봉 전체를 사용할 수 있는 최초 시점: `available_time_us = close_time_exclusive_us`
- Binance 원본의 close time은 `source_close_time_us`에 그대로 보존
- 2025-01-01 이후 Binance Spot 원본의 microsecond 전환을 자동 감지
- 결측 봉은 가격으로 채우지 않음. 품질 리포트에 명시
- 정확히 같은 중복은 감사 수량을 남기고 제거; 충돌 중복은 격리 대상 오류
- 불완전한 상위 시간봉은 생성하지 않음

자세한 계약은 [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md)와 [`docs/BACKTEST_SEMANTICS.md`](docs/BACKTEST_SEMANTICS.md)를 참조하십시오.

## 저장 구조

```text
Google Drive / SMC_ICT_3_LIVE
├── 00_README
├── 01_RAW_BRONZE          # 원본 ZIP + .CHECKSUM, 불변
├── 02_NORMALIZED_SILVER   # 검증된 1m 논리 데이터셋
├── 03_DERIVED_GOLD        # 결정적 상위 시간봉·연구용 뷰
├── 04_CATALOG_QUALITY     # 매니페스트, 해시, 결측/중복 리포트
├── 05_RELEASES            # 고정 버전 배포 번들
├── 90_QUARANTINE          # 충돌·체크섬 불일치·계약 위반
└── 99_ARCHIVE             # 폐기하지 않고 보존한 이전 릴리스
```

Git 저장소에는 `data/raw`, `data/silver`, `data/gold`를 커밋하지 않습니다. 데이터와 코드를 분리함으로써 Git 이력을 가볍게 유지하고, 데이터 릴리스는 별도 해시와 매니페스트로 고정합니다.

## 배포된 데이터 릴리스

프로젝트 Drive: <https://drive.google.com/drive/folders/13jbg62qO6LkFHO0apvLEDhOSZBdbm_c1>

### `golden-2024-01-v1.0.0`

- 기간: `[2024-01-01, 2024-02-01)` UTC
- 원천: 4개 심볼 × Spot 거래가 + USD-M 거래가·mark·index·premium = 20개 공식 월간 ZIP
- Bronze/Silver: 공식 체크섬 통과 20개, 정규화 1분 레코드 892,800개
- 품질: 정확 중복 0개, 결측 봉 0개
- Gold: 5m·15m·1h·4h 80개 파일, 256,680개 레코드, 불완전 버킷 0개
- 공식 CI 전체 번들: <https://drive.google.com/file/d/15fJ3v2pHF9ctUaQQHy6XxGy8qCxjJKAw/view>
- 릴리스 폴더: <https://drive.google.com/drive/folders/159EwwmXK8Ef-u0islmiPdUHMxJmglgFC>
- 고정 인덱스와 SHA-256: [`data/releases/golden-2024-01-v1.0.0.json`](data/releases/golden-2024-01-v1.0.0.json)

Bronze·Silver·Gold·품질 번들은 각각 해당 Drive 계층에도 배치되어 있습니다. 연구 코드는 사람이 보기에 같은 파일명을 찾지 말고 릴리스 ID와 SHA-256을 함께 고정해야 합니다.

## 빠른 시작

Python 3.11 이상이면 계획·다운로드·검증·CSV.gz 생성에 외부 패키지가 필요하지 않습니다.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
smc-data doctor
```

2024년 1월 골든 릴리스 후보를 재생성합니다.

```bash
smc-data plan \
  --start 2024-01-01 \
  --end 2024-01-31 \
  --as-of 2024-02-12 \
  --out data/manifests/golden_2024_01.csv
```

원본을 내려받아 검증·정규화·카탈로그화합니다.

```bash
mkdir -p work/{raw,silver,quality,catalog}
smc-data build \
  --manifest data/manifests/golden_2024_01.csv \
  --data-root work \
  --raw-root work/raw \
  --silver-root work/silver \
  --quality-root work/quality \
  --download-report work/quality/download_report.jsonl \
  --catalog work/catalog/catalog.csv
```

1m Silver를 5m로 파생하는 예입니다.

```bash
smc-data resample \
  --input path/to/BTCUSDT-1m-2024-01.csv.gz \
  --target 5m \
  --output path/to/BTCUSDT-5m-2024-01.csv.gz \
  --report path/to/BTCUSDT-5m-2024-01.quality.json
```

## 매니페스트

- `data/manifests/golden_2024_01.csv`: 4개 자산 × 5개 기본 데이터셋 = 20개 월간 원본
- `data/manifests/full_history_candidates_2026-08-02.sha256`: Drive에 배포한 2,900개 전체 이력 후보 매니페스트의 고정 해시·행 수

전체 CSV는 Google Drive `04_CATALOG_QUALITY/manifests`에 두며 다음 명령으로 byte-for-byte 재생성할 수 있습니다.

```bash
smc-data plan --start 2017-01-01 --end 2026-07-31 --as-of 2026-08-02 \
  --out full_history_candidates_2026-08-02.csv
```

후보 매니페스트는 상장일을 추측하지 않습니다. 다운로드 시 `.CHECKSUM`의 존재 여부로 원천 가용성을 판정하며 404를 `source_unavailable`로 기록합니다. 이 방식은 연구자가 임의 시작일로 생존 종목만 남기는 실수를 줄입니다.

## 품질 게이트

`pytest` 계약 테스트는 다음을 검사합니다.

1. 공식 URL·월간/일간 전환 규칙
2. seconds/ms/us/ns 타임스탬프 정규화
3. OHLC·거래량·거래 건수 제약
4. 정확 중복 제거와 충돌 중복 거부
5. 결측 탐지와 무보간 원칙
6. 참조가격 보조 필드의 의미 분리
7. premium index의 정상적인 음수 허용과 mark/index/trade 가격의 비음수 제약
8. 불완전 버킷 제거
9. byte-deterministic gzip 출력
10. 골든 매니페스트 재현성

## 연구자 경계

이 저장소는 **시장 데이터 계층**입니다. BOS, CHoCH, displacement, liquidity sweep, FVG, order block, premium/discount, session bias 같은 SMC/ICT 판단을 Silver 데이터에 미리 새기지 않습니다. 패턴 검출과 시나리오 상태 머신은 별도 연구 계층에서 데이터 버전과 함께 실행해야 합니다.

소스 비교와 선택 근거는 [`docs/SOURCE_RESEARCH.md`](docs/SOURCE_RESEARCH.md), 운영·릴리스 절차는 [`docs/OPERATIONS.md`](docs/OPERATIONS.md), 연구자가 지켜야 할 규칙은 [`docs/RESEARCHER_GUIDE.md`](docs/RESEARCHER_GUIDE.md)에 있습니다.
