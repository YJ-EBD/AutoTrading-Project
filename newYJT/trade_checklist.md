# newYJT Trade Checklist

## 완료

- `settings.env` 로드 및 모드 분기
- 실제 Binance USD-M 계정 잔고 조회
- 실제 Binance 포지션 조회
- 실제 Binance 오픈 오더 조회
- 실제 Binance user trades 조회
- 최소 주문금액 / 심볼 제약 검증
- `/fapi/v1/order/test` 기반 테스트 오더 검증
- 시뮬레이션 오픈 포지션 -> `binanceTrade.py` 주문 프리뷰 생성
- 동적 스테이크: 실제 가용 잔고의 비율 사용
- TP / SL 프리뷰 계산
- 웹에서 아래 정보 표시
  - 실제 총 잔고 / 가용 잔고 / 포지션 수
  - 실제 최근 체결 수 / 실현손익 / 수수료
  - 실제 포지션 / 실제 오픈 오더 / 실제 최근 체결
  - 시뮬레이션 전적 / 활성 포지션 / 최근 종료 포지션
  - trade shadow 프리뷰

## 의도적으로 막아둔 부분

- 실제 주문 제출
- 실제 TP / SL 실주문 제출
- 실제 포지션 자동 청산 주문 제출

## 실주문 차단 위치

- `newYJT/binanceTrade.py`
  - `BinanceFuturesClient._request()`
  - `POST`, `PUT`, `PATCH`, `DELETE` 요청은 `allow_mutating_requests = false`일 때 네트워크로 보내지지 않음
- `newYJT/scripts/render_runtime_configs.py`
  - `BLOCK_REAL_ORDER_SUBMISSION=true`면 `live_preflight` 유지

## 관련 파일

- `newYJT/binanceTrade.py`
- `newYJT/scripts/settings_env.py`
- `newYJT/scripts/render_runtime_configs.py`
- `newYJT/scripts/live_preflight.py`
- `newYJT/scripts/generate_binance_trade_shadow_status.py`
- `newYJT/scripts/generate_freqtrade_status.py`
- `newYJT/scripts/run_binance_trade_shadow_loop.py`
- `newYJT/scripts/run_live_preflight_loop.py`
- `newYJT/scripts/run_newyjt_console.py`
- `newYJT/index.html`


## 현재 라이브 동작

- `settings.env` 에서 `ENABLE_LIVE_TRADING=true` 이면 대시보드가 보여주는 freqtrade 런타임이 실제 Binance USD-M 계정으로 전환됨
- dry-run / live 모두 같은 freqtrade 전략 로직과 동일한 상태 JSON / 웹 표시 구조를 사용함
- `newYJT/binanceTrade.py` 도 같은 스위치를 따르며, live일 때만 state-changing Binance REST 요청을 허용함
- LLM vendor 루프는 기본적으로 simulation 유지 (`ENABLE_LLM_LIVE_TRADING=false`)
