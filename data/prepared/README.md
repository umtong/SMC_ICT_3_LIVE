# Prepared research data

`CURRENT`가 이 저장소에 커밋된 검증 완료 기본 릴리스를 가리킵니다.
연구자는 이를 직접 사용하며 Google Drive 마운트나 외부 시장 데이터 다운로드가 필요하지 않습니다.

모든 카탈로그 파일의 크기와 SHA-256을 검사합니다.

```bash
PYTHONPATH=src python3 -m smc_ict_data.cli ready --verify
```
