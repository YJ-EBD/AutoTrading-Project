# 파일 설명서

## 루트 파일

- `README.md`: 프로젝트 소개, 빠른 시작 명령, 주요 문서 링크를 제공합니다.
- `pyproject.toml`: 패키지 메타데이터, 의존성, setuptools 설정, pytest 설정을 담습니다.
- `protocol`: 자주 쓰는 PowerShell 명령을 적어둔 로컬 작업 메모입니다.
- `.gitignore`: 로컬 가상환경과 Python 캐시 산출물을 Git 추적에서 제외합니다.

## 설정과 문서

- `configs/base.yaml`: 거래소, 백테스트, ML, 포트폴리오, 배포, 페이퍼 런타임, 대시보드, LLM, 자동 루프 설정의 기준 파일입니다.
- `docs/architecture.md`: 전체 아키텍처 레이어와 검증 철학을 간단히 정리합니다.
- `docs/runbook.md`: 운영자가 바로 실행할 수 있는 명령과 운영 흐름을 설명합니다.
- `docs/usage_guide.md`: 설치, 연구 실행, 배포, 대시보드, 자동 재튜닝 사용법을 단계별로 설명합니다.
- `docs/implementation_overview.md`: 현재 구현된 기능, 흐름, 가정, 한계를 요약합니다.
- `docs/file_reference.md`: 추적 대상 파일별 역할을 설명합니다.

## 패키지 루트

- `src/binance_quant/__init__.py`: 메인 패키지 네임스페이스를 선언합니다.
- `src/binance_quant/cli.py`: 연구, 배포, 페이퍼 런타임, 대시보드, 자동 루프 명령을 연결하는 CLI 진입점입니다.
- `src/binance_quant/config.py`: dataclass 기반 설정 스키마, YAML 로딩, 경로 해석을 담당합니다.
- `src/binance_quant/storage.py`: 디스크 캐시와 파일 저장 보조 기능을 제공합니다.
- `src/binance_quant/utils.py`: UTC 시각 처리 등 공통 유틸리티를 제공합니다.

## 백테스트 레이어

- `src/binance_quant/backtest/__init__.py`: 백테스트 패키지 표시 파일입니다.
- `src/binance_quant/backtest/engine.py`: 레버리지, 수수료, 슬리피지, TP, SL, horizon, liquidation을 포함한 백테스트 엔진입니다.
- `src/binance_quant/backtest/metrics.py`: 수익률, 드로다운, 팩터 등 성과 지표 계산을 담당합니다.

## 데이터 레이어

- `src/binance_quant/data/__init__.py`: 데이터 패키지 표시 파일입니다.
- `src/binance_quant/data/ingestion.py`: 과거 kline 백필, 증분 업데이트, parquet 저장, 무결성 검사를 수행합니다.
- `src/binance_quant/data/live.py`: 실시간 kline 웹소켓 스트림, 재연결, 회전, 상태 콜백을 담당합니다.
- `src/binance_quant/data/quality.py`: 시간 정렬, 누락 검사, timeframe 보조 함수를 제공합니다.

## 거래소 레이어

- `src/binance_quant/exchange/__init__.py`: 거래소 패키지 표시 파일입니다.
- `src/binance_quant/exchange/client.py`: 공개 Binance REST 호출, 재시도, 캐시, 요청 예산 연동을 처리합니다.
- `src/binance_quant/exchange/models.py`: 거래소 메타데이터 구조체를 정의합니다.
- `src/binance_quant/exchange/rate_limit.py`: 요청 가중치 예산과 쿨다운 로직을 관리합니다.
- `src/binance_quant/exchange/universe.py`: 유니버스 탐색, 심볼 필터링, 메타데이터 스냅샷 저장을 담당합니다.

## 피처와 라벨링 레이어

- `src/binance_quant/features/__init__.py`: 피처 패키지 표시 파일입니다.
- `src/binance_quant/features/engine.py`: OHLCV 프레임과 이벤트 레벨 ML 입력 피처를 생성합니다.
- `src/binance_quant/labeling/__init__.py`: 라벨링 패키지 표시 파일입니다.
- `src/binance_quant/labeling/triple_barrier.py`: 이벤트 라벨과 triple-barrier 스타일 결과를 계산합니다.

## 로컬 LLM 레이어

- `src/binance_quant/llm/__init__.py`: 로컬 LLM 패키지 표시 파일입니다.
- `src/binance_quant/llm/ollama.py`: Ollama 호출, 프롬프트 구성, allow 또는 reject 또는 defer 결과 파싱을 담당합니다.

## ML 레이어

- `src/binance_quant/ml/__init__.py`: ML 패키지 표시 파일입니다.
- `src/binance_quant/ml/deployment.py`: 배포 번들 생성, 로드, 페이퍼 추론용 패키징을 담당합니다.
- `src/binance_quant/ml/modeling.py`: 워크포워드 학습, 확률 보정, 모델 비교, fold 평가, 최종 모델 선택을 수행합니다.
- `src/binance_quant/ml/splits.py`: 시계열 안전 분할과 embargo 경계를 생성합니다.
- `src/binance_quant/ml/thresholds.py`: take 또는 skip threshold 탐색 유틸리티입니다.

## 오케스트레이션 레이어

- `src/binance_quant/orchestration/__init__.py`: 오케스트레이션 패키지 표시 파일입니다.
- `src/binance_quant/orchestration/auto_loop.py`: mutation 시퀀스를 돌리는 자동 개선 루프입니다.
- `src/binance_quant/orchestration/research_loop.py`: sanity check부터 리포트와 승격 게이트까지의 전체 연구 엔진입니다.
- `src/binance_quant/orchestration/weekly_refresh.py`: 주간 리프레시 실행 보조 파일입니다.

## 페이퍼 트레이딩 레이어

- `src/binance_quant/paper/__init__.py`: 페이퍼 트레이딩 패키지 표시 파일입니다.
- `src/binance_quant/paper/dashboard.py`: FastAPI 앱 생성, 대시보드 라우트, 상태 API, 로그 API를 담당합니다.
- `src/binance_quant/paper/logging_utils.py`: 파일 로그 핸들러 설정과 로그 tail 읽기를 담당합니다.
- `src/binance_quant/paper/models.py`: 페이퍼 의사결정, 포지션, 재튜닝 이벤트 dataclass를 정의합니다.
- `src/binance_quant/paper/repository.py`: SQLite 기반 의사결정, 포지션, 런타임 상태 저장소입니다.
- `src/binance_quant/paper/runtime.py`: 실시간 페이퍼 런타임, 일일 재튜닝, 웹소켓 소비, 포지션 갱신의 핵심 엔진입니다.
- `src/binance_quant/paper/templates/dashboard.html`: 한국어 대시보드 UI 템플릿입니다.

## 포트폴리오 레이어

- `src/binance_quant/portfolio/__init__.py`: 포트폴리오 패키지 표시 파일입니다.
- `src/binance_quant/portfolio/engine.py`: 포트폴리오 조립, 분산 제약, 최종 포트폴리오 평가를 담당합니다.

## 리포팅 레이어

- `src/binance_quant/reporting/__init__.py`: 리포팅 패키지 표시 파일입니다.
- `src/binance_quant/reporting/reports.py`: JSON, CSV, Markdown 리포트 생성을 담당합니다.

## 전략 레이어

- `src/binance_quant/strategies/__init__.py`: 전략 패키지 표시 파일입니다.
- `src/binance_quant/strategies/base.py`: 전략 결과와 변형 추상화 공통 구조를 정의합니다.
- `src/binance_quant/strategies/indicators.py`: 전략들이 재사용하는 보조 지표 계산 함수 모음입니다.
- `src/binance_quant/strategies/parity.py`: Pine 의미와 Python 의미가 같은지 검증하는 패리티 도구입니다.
- `src/binance_quant/strategies/templates.py`: Pine 스타일 전략군과 파라미터화된 시그널 생성 로직을 담고 있습니다.

## 테스트

- `tests/test_backtest_engine.py`: 백테스트 체결과 종료 동작을 검증합니다.
- `tests/test_config.py`: 설정 로딩과 핵심 기본값을 검증합니다.
- `tests/test_features.py`: 피처 생성과 누수 방지 기대값을 검증합니다.
- `tests/test_paper_dashboard.py`: 대시보드 컨텍스트와 런타임 상태 페이로드를 검증합니다.
- `tests/test_paper_logging.py`: 로그 tail과 paper log 경로 해석을 검증합니다.
- `tests/test_paper_repository.py`: SQLite 저장소의 의사결정과 포지션 저장을 검증합니다.
- `tests/test_portfolio_engine.py`: 포트폴리오 조립과 집중도 제약을 검증합니다.
- `tests/test_research_loop.py`: 연구 루프의 선택과 탈락 로직을 검증합니다.
- `tests/test_splits.py`: 시계열 분할 순서와 embargo를 검증합니다.
- `tests/test_strategy_parity.py`: 전략 패리티 검증이 동작하는지 확인합니다.

## 런타임 데이터 디렉터리

- `data/market/klines/15m/*.parquet`: 연구와 페이퍼 초기화에 사용하는 과거 시장 데이터 저장소입니다.
- `data/cache/*`: 거래소 메타데이터와 요청 캐시입니다.
- `artifacts/<timestamp>/*`: 실험별 리포트, 요약, 진단, 진행 상태, 품질 리포트를 담습니다.
- `artifacts/latest/*`: 최신 포인터, 런타임 로그, 최근 연구 상태를 담습니다.
- `artifacts/deployment/*`: 페이퍼 배포 번들과 매니페스트입니다.
- `artifacts/paper/paper_state.sqlite3`: 페이퍼 의사결정, 포지션, 재튜닝, 서비스 상태를 저장하는 SQLite 데이터베이스입니다.
