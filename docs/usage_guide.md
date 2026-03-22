# 사용 가이드

## 1. 환경 준비

```powershell
cd C:\yjcooperation
python -m pip install -e .[dev]
```

이 프로젝트는 Python `3.12+` 기준으로 동작하며 패키지 이름은 `binance_quant`입니다.

## 2. 로컬 LLM 준비

페이퍼 런타임은 지표 시그널과 ML 필터 뒤에 Ollama 기반 로컬 LLM을 최종 판단 레이어로 사용할 수 있습니다.

```powershell
winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" serve
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" pull qwen3:14b
```

확인 명령:

```powershell
& "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" list
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags | Select-Object -ExpandProperty Content
```

## 3. 핵심 리서치 흐름

### 바이낸스 USD-M 유니버스 탐색

```powershell
python -m binance_quant.cli discover-universe --config configs\base.yaml
```

출력:

- `artifacts/latest/universe/*`
- 캐시된 거래소 메타데이터
- 캐시된 24시간 티커 스냅샷

### 15분봉 과거 데이터 적재

```powershell
python -m binance_quant.cli backfill --config configs\base.yaml
```

출력:

- `data/market/klines/15m/*.parquet`
- 실험별 심볼 품질 리포트

### 리서치 루프 실행

```powershell
python -m binance_quant.cli run-research --config configs\base.yaml
```

이 명령은 아래 순서를 한 번에 실행합니다.

1. Pine/Python 시그널 패리티 확인
2. 유니버스 탐색
3. 시장 데이터 적재
4. 전략 생성과 프리스크린
5. 이벤트 라벨링과 피처 생성
6. 워크포워드 ML 학습과 확률 보정
7. threshold 탐색
8. 강건성 탈락 판정
9. 제약 기반 포트폴리오 조립
10. 실험 결과와 리포트 저장

### 페이퍼 배포 번들 생성

```powershell
python -m binance_quant.cli build-deployment --config configs\base.yaml
```

출력:

- `artifacts/deployment/paper_bundle.pkl`
- `artifacts/deployment/paper_manifest.json`

## 4. 페이퍼 트레이딩 런타임

### 런타임만 실행

```powershell
python -m binance_quant.cli paper-runtime --config configs\base.yaml
```

이 모드는 다음을 수행합니다.

- 바이낸스 15분봉 웹소켓 수신
- 지표 기반 시그널 평가
- 학습된 ML 필터로 진입 확률 계산
- 필요 시 Ollama 최종 판단 수행
- 시그널 시점 관측가로 페이퍼 포지션 오픈
- TP, SL, 강제청산, 보유기간 종료, 시그널 종료 시 관측가로 종료 기록
- 모든 의사결정과 포지션 상태를 SQLite에 저장

### FastAPI 대시보드 실행

```powershell
python -m binance_quant.cli serve-paper --config configs\base.yaml
```

기본 주소:

- `http://127.0.0.1:8000`

주요 API:

- `/api/overview`
- `/api/status`
- `/api/logs`
- `/api/positions/active`
- `/api/positions/closed`
- `/api/decisions`
- `/api/retunes`
- `/api/runtime/start`
- `/api/runtime/stop`

## 5. 자동 루프

### 주간 리프레시

```powershell
python -m binance_quant.cli weekly-refresh --config configs\base.yaml
```

### 횟수 제한 자동 개선 루프

```powershell
python -m binance_quant.cli auto-loop --config configs\base.yaml
```

### 연속 무한 루프

```powershell
python -m binance_quant.cli continuous-loop --config configs\base.yaml
```

연속 루프는 승격 게이트를 통과하거나 `artifacts/latest/STOP_AUTO_LOOP` 파일이 생길 때까지 계속 반복합니다.

## 6. 매일 자동 튜닝과 재학습

현재 `configs/base.yaml` 기본값은 아래와 같습니다.

- `paper.auto_retune: true`
- `paper.retune_interval_hours: 24`
- `paper.retune_check_seconds: 300`
- `paper.initial_retune_delay_seconds: 90`
- `paper.auto_rebuild_deployment: true`

의미는 다음과 같습니다.

1. 서버 시작 후 짧은 예열 시간을 둡니다.
2. 5분마다 마지막 재튜닝 완료 시각을 확인합니다.
3. 24시간이 지나면 전체 리서치 루프를 다시 실행합니다.
4. 새 후보가 `accepted_for_paper`를 통과하면 배포 번들을 자동 재생성합니다.
5. 페이퍼 런타임은 새 번들 기준으로 스트림 대상을 다시 반영합니다.

## 7. 로그와 상태 저장 위치

주요 로컬 저장 위치:

- `artifacts/paper/paper_state.sqlite3`
- `artifacts/latest/paper_runtime.log`
- `artifacts/deployment/paper_manifest.json`
- `artifacts/deployment/paper_bundle.pkl`
- `artifacts/latest/research_summary.json`
- `artifacts/latest/research_progress.json`

## 8. 테스트 명령

```powershell
python -m pytest
python -m compileall src
```

## 9. Git 동기화 주의사항

GitHub에는 프로젝트 자체를 올리고, 로컬 가상환경은 올리지 않는 것이 맞습니다. `.venv`는 100MB를 넘는 바이너리를 포함해 GitHub 제한에 걸리므로 `.gitignore`로 제외했습니다.
