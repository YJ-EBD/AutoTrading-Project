from __future__ import annotations

import base64
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logic.settings_env import load_settings_env, resolve_freqtrade_db_path
from model.registry import FREQAI_MODEL_NAME, FREQAI_STRATEGY_NAME

CONFIG_PATH = ROOT / "runtime" / "freqtrade" / "config.binance_usdtm.freqai.json"
STATUS_PATH = ROOT / "runtime" / "status.json"
SETTINGS_STATE_PATH = ROOT / "runtime" / "settings_state.json"
LIVE_PREFLIGHT_PATH = ROOT / "runtime" / "live_preflight.json"
TRADE_SHADOW_PATH = ROOT / "runtime" / "binance_trade_shadow.json"
DATA_DIR = ROOT / "runtime" / "freqtrade" / "user_data" / "data" / "binance" / "futures"
RESOLVED_PAIRS_PATH = ROOT / "runtime" / "resolved_pairs.json"
ACTIVE_PAIRS_PATH = ROOT / "runtime" / "active_pairs.json"
ACTIVE_PAIR_SCORES_PATH = ROOT / "runtime" / "active_pair_scores.json"
LIVE_ACCOUNT_STATE_PATH = ROOT / "runtime" / "live_account_state.json"
SETTINGS_ENV_PATH = ROOT / "settings.env"
PIPELINE_STAGE_SNAPSHOT_PATH = ROOT / "runtime" / "pipeline_stage_snapshot.json"
TUNING_STATE_PATH = ROOT / "runtime" / "tuning_state.json"
COMPONENT_SNAPSHOT_PATH = ROOT / "runtime" / "freqai_component_snapshot.json"
LLM_SIGNAL_SNAPSHOT_PATH = ROOT / "runtime" / "llm_signal_snapshot.json"
LOCAL_TIMEZONE = ZoneInfo("Asia/Seoul")
LEVERAGE_ROI_PROFILES = (
    (5.0, [
        {"label": "0-20m", "max_duration_min": 20, "target_pct": 4.4},
        {"label": "20-60m", "max_duration_min": 60, "target_pct": 3.2},
        {"label": "60-180m", "max_duration_min": 180, "target_pct": 2.3},
        {"label": "180-480m", "max_duration_min": 480, "target_pct": 1.6},
        {"label": "480-720m", "max_duration_min": 720, "target_pct": 1.1},
        {"label": "720m+", "max_duration_min": None, "target_pct": 0.7},
    ]),
    (4.0, [
        {"label": "0-20m", "max_duration_min": 20, "target_pct": 3.8},
        {"label": "20-60m", "max_duration_min": 60, "target_pct": 2.8},
        {"label": "60-180m", "max_duration_min": 180, "target_pct": 2.0},
        {"label": "180-480m", "max_duration_min": 480, "target_pct": 1.4},
        {"label": "480-720m", "max_duration_min": 720, "target_pct": 0.95},
        {"label": "720m+", "max_duration_min": None, "target_pct": 0.6},
    ]),
    (3.0, [
        {"label": "0-20m", "max_duration_min": 20, "target_pct": 3.3},
        {"label": "20-60m", "max_duration_min": 60, "target_pct": 2.4},
        {"label": "60-180m", "max_duration_min": 180, "target_pct": 1.7},
        {"label": "180-480m", "max_duration_min": 480, "target_pct": 1.2},
        {"label": "480-720m", "max_duration_min": 720, "target_pct": 0.8},
        {"label": "720m+", "max_duration_min": None, "target_pct": 0.5},
    ]),
    (1.0, [
        {"label": "0-20m", "max_duration_min": 20, "target_pct": 2.8},
        {"label": "20-60m", "max_duration_min": 60, "target_pct": 2.0},
        {"label": "60-180m", "max_duration_min": 180, "target_pct": 1.4},
        {"label": "180-480m", "max_duration_min": 480, "target_pct": 1.0},
        {"label": "480-720m", "max_duration_min": 720, "target_pct": 0.7},
        {"label": "720m+", "max_duration_min": None, "target_pct": 0.4},
    ]),
)
LEVERAGE_PROFIT_LOCK_PROFILES = (
    (5.0, [
        {"min_profit_pct": 1.3, "stoploss_pct": 1.5},
        {"min_profit_pct": 2.2, "stoploss_pct": 1.1},
        {"min_profit_pct": 3.2, "stoploss_pct": 0.8},
        {"min_profit_pct": 4.6, "stoploss_pct": 0.6},
        {"min_profit_pct": 6.2, "stoploss_pct": 0.4},
        {"min_profit_pct": 8.0, "stoploss_pct": 0.25},
    ]),
    (4.0, [
        {"min_profit_pct": 1.2, "stoploss_pct": 1.7},
        {"min_profit_pct": 2.0, "stoploss_pct": 1.25},
        {"min_profit_pct": 2.9, "stoploss_pct": 0.95},
        {"min_profit_pct": 4.1, "stoploss_pct": 0.7},
        {"min_profit_pct": 5.6, "stoploss_pct": 0.45},
        {"min_profit_pct": 7.2, "stoploss_pct": 0.3},
    ]),
    (3.0, [
        {"min_profit_pct": 1.1, "stoploss_pct": 1.9},
        {"min_profit_pct": 1.9, "stoploss_pct": 1.45},
        {"min_profit_pct": 2.8, "stoploss_pct": 1.1},
        {"min_profit_pct": 4.0, "stoploss_pct": 0.8},
        {"min_profit_pct": 5.3, "stoploss_pct": 0.55},
        {"min_profit_pct": 6.8, "stoploss_pct": 0.35},
    ]),
    (1.0, [
        {"min_profit_pct": 1.0, "stoploss_pct": 2.0},
        {"min_profit_pct": 1.8, "stoploss_pct": 1.6},
        {"min_profit_pct": 2.8, "stoploss_pct": 1.3},
        {"min_profit_pct": 4.0, "stoploss_pct": 1.0},
        {"min_profit_pct": 5.5, "stoploss_pct": 0.7},
        {"min_profit_pct": 7.0, "stoploss_pct": 0.4},
    ]),
)


def _build_engine_summary(config: dict, settings_state: dict | None = None) -> dict:
    freqai_config = config.get("freqai", {})
    training_parameters = freqai_config.get("model_training_parameters", {})
    ensemble_weights = training_parameters.get("ensemble_weights", {})
    xgb_weight = ensemble_weights.get("xgboost")
    pytorch_weight = ensemble_weights.get("pytorch")
    hybrid_mode = "Hybrid" in FREQAI_MODEL_NAME
    settings_state = settings_state or {}
    llm_provider = str(settings_state.get("llm_provider") or ("anthropic" if settings_state.get("anthropic_key_present") else "ollama"))
    llm_model = settings_state.get("llm_model")
    llm_fallback_model = settings_state.get("llm_fallback_model")
    llm_market_type = settings_state.get("llm_market_type")
    return {
        "freqai_model": FREQAI_MODEL_NAME,
        "strategy": FREQAI_STRATEGY_NAME,
        "identifier": freqai_config.get("identifier"),
        "hybrid_mode": hybrid_mode,
        "ml_enabled": True,
        "dl_enabled": hybrid_mode,
        "llm_enabled": True,
        "ml_component": "XGBoostClassifier",
        "dl_component": "PyTorchMLPClassifier" if hybrid_mode else None,
        "llm_component": f"{llm_provider.title()}PatternVeto",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_fallback_model": llm_fallback_model,
        "llm_market_type": llm_market_type,
        "ensemble_weights": {
            "xgboost": _round(xgb_weight, 4) if xgb_weight is not None else None,
            "pytorch": _round(pytorch_weight, 4) if pytorch_weight is not None else None,
        },
    }


def _round(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _compute_excursion_pcts(
    open_rate: float | None,
    max_rate: float | None,
    min_rate: float | None,
    *,
    is_short: bool,
    leverage: float | None,
) -> tuple[float | None, float | None]:
    if open_rate is None:
        return None, None
    open_rate_f = float(open_rate)
    if open_rate_f <= 0:
        return None, None

    leverage_f = max(float(leverage or 1.0), 1.0)
    max_rate_f = float(max_rate if max_rate is not None else open_rate_f)
    min_rate_f = float(min_rate if min_rate is not None else open_rate_f)

    if is_short:
        max_tp_pct = ((open_rate_f - min_rate_f) / open_rate_f) * leverage_f * 100.0
        max_sl_pct = ((open_rate_f - max_rate_f) / open_rate_f) * leverage_f * 100.0
    else:
        max_tp_pct = ((max_rate_f - open_rate_f) / open_rate_f) * leverage_f * 100.0
        max_sl_pct = ((min_rate_f - open_rate_f) / open_rate_f) * leverage_f * 100.0

    return max_tp_pct, max_sl_pct


def _safe_fetchone(cur: sqlite3.Cursor, query: str, default=0):
    row = cur.execute(query).fetchone()
    if not row:
        return default
    return row[0] if row[0] is not None else default


def _deserialize_custom_value(raw: str | None, value_type: str | None):
    if raw is None:
        return None
    value_type = str(value_type or "").strip()
    if value_type == "bool":
        return str(raw).strip().lower() in {"1", "true", "yes", "on"}
    if value_type == "int":
        try:
            return int(raw)
        except ValueError:
            return 0
    if value_type == "float":
        try:
            return float(raw)
        except ValueError:
            return 0.0
    if value_type == "NoneType":
        return None
    if value_type in {"list", "dict", "tuple"}:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def _load_trade_custom_data_map(cur: sqlite3.Cursor, trade_ids: list[int]) -> dict[int, dict]:
    if not trade_ids:
        return {}
    placeholders = ",".join("?" for _ in trade_ids)
    rows = cur.execute(
        f"""
        select ft_trade_id, cd_key, cd_type, cd_value
        from trade_custom_data
        where ft_trade_id in ({placeholders})
        """,
        trade_ids,
    ).fetchall()
    payload: dict[int, dict] = {}
    for row in rows:
        trade_id = int(row["ft_trade_id"])
        payload.setdefault(trade_id, {})[row["cd_key"]] = _deserialize_custom_value(
            row["cd_value"],
            row["cd_type"],
        )
    return payload


def _parse_trade_datetime(raw: str | None) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _current_roi_target_pct(
    open_date: str | None,
    roi_schedule: list[dict],
    *,
    now_utc: datetime | None = None,
) -> float | None:
    opened_at = _parse_trade_datetime(open_date)
    if opened_at is None:
        return None
    now_utc = now_utc or datetime.now(timezone.utc)
    trade_age_minutes = max((now_utc - opened_at).total_seconds() / 60.0, 0.0)
    for band in roi_schedule:
        if not isinstance(band, dict):
            continue
        max_duration = band.get("max_duration_min")
        target_pct = band.get("target_pct")
        if target_pct is None:
            continue
        if max_duration is None or trade_age_minutes < float(max_duration):
            return _round(target_pct, 4)
    return None


def _roi_schedule_for_leverage(leverage: float | None) -> list[dict]:
    leverage_value = max(float(leverage or 1.0), 1.0)
    for min_leverage, schedule in LEVERAGE_ROI_PROFILES:
        if leverage_value >= min_leverage:
            return schedule
    return LEVERAGE_ROI_PROFILES[-1][1]


def _profit_lock_schedule_for_leverage(leverage: float | None) -> list[dict]:
    leverage_value = max(float(leverage or 1.0), 1.0)
    for min_leverage, schedule in LEVERAGE_PROFIT_LOCK_PROFILES:
        if leverage_value >= min_leverage:
            return schedule
    return LEVERAGE_PROFIT_LOCK_PROFILES[-1][1]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _pair_to_symbol(pair: str | None) -> str | None:
    if not pair:
        return None
    return str(pair).replace("/USDT:USDT", "USDT").replace("/", "")


def _symbol_to_pair(symbol: str | None) -> str | None:
    if not symbol:
        return None
    symbol_text = str(symbol).strip().upper()
    if not symbol_text.endswith("USDT"):
        return None
    base = symbol_text[:-4]
    if not base:
        return None
    return f"{base}/USDT:USDT"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_config() -> dict:
    return _load_json(CONFIG_PATH)


def _resolve_db_path() -> Path:
    settings = load_settings_env(SETTINGS_ENV_PATH)
    return resolve_freqtrade_db_path(ROOT, settings)


def _load_resolved_pairs() -> list[str]:
    pairs = _load_json(RESOLVED_PAIRS_PATH).get("pairs", [])
    return pairs if isinstance(pairs, list) else []


def _load_active_pairs() -> list[str]:
    pairs = _load_json(ACTIVE_PAIRS_PATH).get("pairs", [])
    return pairs if isinstance(pairs, list) else []


def _load_active_pair_scores() -> dict:
    payload = _load_json(ACTIVE_PAIR_SCORES_PATH)
    return payload if isinstance(payload, dict) else {}


def _empty_pipeline_summary() -> dict:
    return {
        "generated_at": None,
        "evaluated_pairs": 0,
        "final_candidates": 0,
        "final_candidate_pairs": [],
        "stages": {
            "strategy": {"label": "Strategy", "evaluated_count": 0, "pass_count": 0, "blocked_count": 0, "passed_pairs": [], "blocked_pairs": []},
            "ml": {"label": "ML", "evaluated_count": 0, "pass_count": 0, "blocked_count": 0, "passed_pairs": [], "blocked_pairs": []},
            "dl": {"label": "DL", "evaluated_count": 0, "pass_count": 0, "blocked_count": 0, "passed_pairs": [], "blocked_pairs": []},
            "llm": {"label": "LLM", "evaluated_count": 0, "pass_count": 0, "blocked_count": 0, "passed_pairs": [], "blocked_pairs": []},
        },
    }


def _build_pipeline_summary(active_pairs: list[str]) -> dict:
    snapshot = _load_json(PIPELINE_STAGE_SNAPSHOT_PATH)
    pair_map = snapshot.get("pairs", {})
    if not isinstance(pair_map, dict):
        return _empty_pipeline_summary()

    ordered_pairs = active_pairs or sorted(pair_map.keys())
    records = [pair_map[pair] for pair in ordered_pairs if isinstance(pair_map.get(pair), dict)]
    if not records:
        return _empty_pipeline_summary()

    def _selected(record: dict) -> dict:
        selected = record.get("selected", {})
        return selected if isinstance(selected, dict) else {}

    def _stage_payload(label: str, evaluated: list[dict], attr: str) -> dict:
        passed = [record for record in evaluated if _selected(record).get(attr)]
        blocked = [record for record in evaluated if not _selected(record).get(attr)]
        return {
            "label": label,
            "evaluated_count": len(evaluated),
            "pass_count": len(passed),
            "blocked_count": len(blocked),
            "passed_pairs": [record.get("pair") for record in passed[:5]],
            "blocked_pairs": [
                {
                    "pair": record.get("pair"),
                    "reason": _selected(record).get("blocked_reason") or "blocked",
                }
                for record in blocked[:5]
            ],
        }

    strategy_evaluated = records
    ml_evaluated = [record for record in strategy_evaluated if _selected(record).get("strategy_pass")]
    dl_evaluated = [record for record in ml_evaluated if _selected(record).get("ml_pass")]
    llm_evaluated = [record for record in dl_evaluated if _selected(record).get("dl_pass")]
    final_candidates = [record for record in llm_evaluated if _selected(record).get("llm_pass")]

    return {
        "generated_at": snapshot.get("generated_at"),
        "evaluated_pairs": len(records),
        "final_candidates": len(final_candidates),
        "final_candidate_pairs": [record.get("pair") for record in final_candidates[:10]],
        "stages": {
            "strategy": _stage_payload("Strategy", strategy_evaluated, "strategy_pass"),
            "ml": _stage_payload("ML", ml_evaluated, "ml_pass"),
            "dl": _stage_payload("DL", dl_evaluated, "dl_pass"),
            "llm": _stage_payload("LLM", llm_evaluated, "llm_pass"),
        },
    }


def _empty_tuning_summary() -> dict:
    return {
        "active": False,
        "label": None,
        "strategy_version": None,
        "applied_at": None,
        "baseline_trade_id": None,
        "carryover_open_trade_ids": [],
        "carryover_open_trades_count": 0,
        "notes": [],
        "stats_since_tuning": {
            "total_trades": 0,
            "open_trades": 0,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "gross_profit_abs_usd": 0.0,
            "fees_paid_usd": 0.0,
            "profit_abs_usd": 0.0,
            "profit_factor": 0.0,
        },
    }


def _build_tuning_summary(cur: sqlite3.Cursor) -> dict:
    tuning_state = _load_json(TUNING_STATE_PATH)
    if not tuning_state:
        return _empty_tuning_summary()

    baseline_trade_id = int(tuning_state.get("baseline_trade_id") or 0)
    carryover_open_trade_ids = tuning_state.get("carryover_open_trade_ids", [])
    if not isinstance(carryover_open_trade_ids, list):
        carryover_open_trade_ids = []
    notes = tuning_state.get("notes", [])
    if not isinstance(notes, list):
        notes = []

    total = _safe_fetchone(cur, f"select count(*) from trades where id > {baseline_trade_id}")
    open_count = _safe_fetchone(cur, f"select count(*) from trades where id > {baseline_trade_id} and is_open = 1")
    closed = _safe_fetchone(cur, f"select count(*) from trades where id > {baseline_trade_id} and is_open = 0")
    wins = _safe_fetchone(
        cur,
        f"select count(*) from trades where id > {baseline_trade_id} and is_open = 0 and coalesce(close_profit_abs, 0) > 0",
    )
    losses = _safe_fetchone(
        cur,
        f"select count(*) from trades where id > {baseline_trade_id} and is_open = 0 and coalesce(close_profit_abs, 0) < 0",
    )
    profit_abs = float(
        _safe_fetchone(
            cur,
            f"select coalesce(sum(close_profit_abs), 0) from trades where id > {baseline_trade_id} and is_open = 0",
            0.0,
        )
    )
    fees_paid_abs = float(
        _safe_fetchone(
            cur,
            f"""
            select coalesce(sum(coalesce(fee_open_cost, 0) + coalesce(fee_close_cost, 0) + coalesce(funding_fees, 0)), 0)
            from trades
            where id > {baseline_trade_id} and is_open = 0
            """,
            0.0,
        )
    )
    gross_profit_abs = profit_abs + fees_paid_abs
    gross_win = float(
        _safe_fetchone(
            cur,
            f"select coalesce(sum(close_profit_abs), 0) from trades where id > {baseline_trade_id} and is_open = 0 and coalesce(close_profit_abs, 0) > 0",
            0.0,
        )
    )
    gross_loss = float(
        _safe_fetchone(
            cur,
            f"select coalesce(sum(close_profit_abs), 0) from trades where id > {baseline_trade_id} and is_open = 0 and coalesce(close_profit_abs, 0) < 0",
            0.0,
        )
    )
    win_rate = (wins / closed * 100.0) if closed else 0.0
    profit_factor = (gross_win / abs(gross_loss)) if gross_loss < 0 else (gross_win if gross_win > 0 else 0.0)

    return {
        "active": True,
        "label": tuning_state.get("label"),
        "strategy_version": tuning_state.get("strategy_version"),
        "applied_at": tuning_state.get("applied_at"),
        "baseline_trade_id": baseline_trade_id,
        "carryover_open_trade_ids": carryover_open_trade_ids,
        "carryover_open_trades_count": len(carryover_open_trade_ids),
        "notes": notes[:10],
        "stats_since_tuning": {
            "total_trades": total,
            "open_trades": open_count,
            "closed_trades": closed,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": _round(win_rate, 2),
            "gross_profit_abs_usd": _round(gross_profit_abs, 4),
            "fees_paid_usd": _round(fees_paid_abs, 4),
            "profit_abs_usd": _round(profit_abs, 4),
            "profit_factor": _round(profit_factor, 4),
        },
    }


def _to_local_datetime(raw: str | None) -> datetime | None:
    parsed = _parse_trade_datetime(raw)
    if parsed is None:
        return None
    return parsed.astimezone(LOCAL_TIMEZONE)


def _pair_asset_label(pair: str | None) -> str:
    if not pair:
        return "-"
    return str(pair).split("/")[0]


def _profit_factor_from_records(records: list[dict]) -> float:
    gross_win = sum(max(float(record.get("net_profit_abs") or 0.0), 0.0) for record in records)
    gross_loss = sum(min(float(record.get("net_profit_abs") or 0.0), 0.0) for record in records)
    if gross_loss < 0:
        return gross_win / abs(gross_loss)
    return gross_win if gross_win > 0 else 0.0


def _summarize_trade_records(records: list[dict], starting_balance: float) -> dict:
    closed_trades = len(records)
    wins = sum(1 for record in records if float(record.get("net_profit_abs") or 0.0) > 0)
    losses = sum(1 for record in records if float(record.get("net_profit_abs") or 0.0) < 0)
    net_profit_abs = sum(float(record.get("net_profit_abs") or 0.0) for record in records)
    fees_abs = sum(float(record.get("fee_total_abs") or 0.0) for record in records)
    gross_profit_abs = net_profit_abs + fees_abs
    avg_roi_pct = (
        sum(float(record.get("profit_pct") or 0.0) for record in records) / closed_trades
        if closed_trades
        else 0.0
    )
    avg_fee_abs = fees_abs / closed_trades if closed_trades else 0.0
    avg_net_profit_abs = net_profit_abs / closed_trades if closed_trades else 0.0
    roi_pct = (net_profit_abs / starting_balance * 100.0) if starting_balance else 0.0
    fee_ratio_pct = (fees_abs / starting_balance * 100.0) if starting_balance else 0.0
    profit_factor = _profit_factor_from_records(records)
    best_trade = max(records, key=lambda record: float(record.get("net_profit_abs") or 0.0), default=None)
    worst_trade = min(records, key=lambda record: float(record.get("net_profit_abs") or 0.0), default=None)

    return {
        "closed_trades": closed_trades,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": _round((wins / closed_trades * 100.0) if closed_trades else 0.0, 2),
        "net_profit_abs_usd": _round(net_profit_abs, 4),
        "gross_profit_abs_usd": _round(gross_profit_abs, 4),
        "fees_abs_usd": _round(fees_abs, 4),
        "avg_roi_pct": _round(avg_roi_pct, 4),
        "avg_fee_abs_usd": _round(avg_fee_abs, 4),
        "avg_net_profit_abs_usd": _round(avg_net_profit_abs, 4),
        "roi_pct": _round(roi_pct, 4),
        "fee_ratio_pct": _round(fee_ratio_pct, 4),
        "profit_factor": _round(profit_factor, 4),
        "best_trade": {
            "trade_id": best_trade.get("id"),
            "pair": best_trade.get("pair"),
            "net_profit_abs": _round(best_trade.get("net_profit_abs"), 4),
            "profit_pct": _round(best_trade.get("profit_pct"), 4),
        } if best_trade else None,
        "worst_trade": {
            "trade_id": worst_trade.get("id"),
            "pair": worst_trade.get("pair"),
            "net_profit_abs": _round(worst_trade.get("net_profit_abs"), 4),
            "profit_pct": _round(worst_trade.get("profit_pct"), 4),
        } if worst_trade else None,
    }


def _build_curve_series(records: list[dict], starting_balance: float) -> list[dict]:
    ordered_records = sorted(
        records,
        key=lambda record: (
            _parse_trade_datetime(record.get("close_date")) or datetime.min.replace(tzinfo=timezone.utc),
            int(record.get("id") or 0),
        ),
    )
    cumulative_profit = 0.0
    cumulative_fee = 0.0
    cumulative_wins = 0
    series: list[dict] = []

    for index, record in enumerate(ordered_records, start=1):
        net_profit_abs = float(record.get("net_profit_abs") or 0.0)
        fee_total_abs = float(record.get("fee_total_abs") or 0.0)
        cumulative_profit += net_profit_abs
        cumulative_fee += fee_total_abs
        if net_profit_abs > 0:
            cumulative_wins += 1
        close_local = _to_local_datetime(record.get("close_date")) or _to_local_datetime(record.get("open_date"))
        label = close_local.strftime("%m-%d %H:%M") if close_local else f"T{record.get('id')}"
        series.append({
            "x": label,
            "x_iso": close_local.isoformat() if close_local else None,
            "trade_id": record.get("id"),
            "pair": record.get("pair"),
            "asset": _pair_asset_label(record.get("pair")),
            "side": record.get("side"),
            "net_profit_abs_usd": _round(net_profit_abs, 4),
            "fee_abs_usd": _round(fee_total_abs, 4),
            "profit_pct": _round(record.get("profit_pct"), 4),
            "cumulative_profit_abs_usd": _round(cumulative_profit, 4),
            "cumulative_fee_abs_usd": _round(cumulative_fee, 4),
            "cumulative_balance_usd": _round((starting_balance + cumulative_profit), 4) if starting_balance else None,
            "cumulative_roi_pct": _round((cumulative_profit / starting_balance * 100.0), 4) if starting_balance else None,
            "cumulative_win_rate_pct": _round((cumulative_wins / index * 100.0), 2),
        })
    return series


def _build_daily_profit_series(records: list[dict], starting_balance: float) -> list[dict]:
    buckets: dict[str, dict] = {}
    for record in records:
        close_local = _to_local_datetime(record.get("close_date")) or _to_local_datetime(record.get("open_date"))
        if close_local is None:
            continue
        key = close_local.strftime("%m-%d")
        bucket = buckets.setdefault(
            key,
            {
                "x": key,
                "date_iso": close_local.date().isoformat(),
                "net_profit_abs_usd": 0.0,
                "fees_abs_usd": 0.0,
                "wins": 0,
                "losses": 0,
                "closed_trades": 0,
                "long_trades": 0,
                "short_trades": 0,
            },
        )
        net_profit_abs = float(record.get("net_profit_abs") or 0.0)
        fee_abs = float(record.get("fee_total_abs") or 0.0)
        bucket["net_profit_abs_usd"] += net_profit_abs
        bucket["fees_abs_usd"] += fee_abs
        bucket["wins"] += 1 if net_profit_abs > 0 else 0
        bucket["losses"] += 1 if net_profit_abs < 0 else 0
        bucket["closed_trades"] += 1
        bucket["long_trades"] += 1 if record.get("side") == "long" else 0
        bucket["short_trades"] += 1 if record.get("side") == "short" else 0

    ordered_keys = sorted(
        buckets.keys(),
        key=lambda key: datetime.strptime(key, "%m-%d"),
    )
    daily_rows = []
    for key in ordered_keys:
        bucket = buckets[key]
        bucket["roi_pct"] = _round((bucket["net_profit_abs_usd"] / starting_balance * 100.0), 4) if starting_balance else 0.0
        bucket["win_rate_pct"] = _round((bucket["wins"] / bucket["closed_trades"] * 100.0), 2) if bucket["closed_trades"] else 0.0
        bucket["net_profit_abs_usd"] = _round(bucket["net_profit_abs_usd"], 4)
        bucket["fees_abs_usd"] = _round(bucket["fees_abs_usd"], 4)
        daily_rows.append(bucket)
    return daily_rows


def _build_pair_details(records: list[dict], starting_balance: float) -> list[dict]:
    pair_groups: dict[str, list[dict]] = {}
    for record in sorted(
        records,
        key=lambda item: (
            _parse_trade_datetime(item.get("close_date")) or datetime.min.replace(tzinfo=timezone.utc),
            int(item.get("id") or 0),
        ),
    ):
        pair_groups.setdefault(str(record.get("pair")), []).append(record)

    pair_details: list[dict] = []
    for pair, pair_records in pair_groups.items():
        stats = _summarize_trade_records(pair_records, starting_balance)
        long_records = [record for record in pair_records if record.get("side") == "long"]
        short_records = [record for record in pair_records if record.get("side") == "short"]
        pair_details.append({
            "pair": pair,
            "asset": _pair_asset_label(pair),
            "stats": {
                **stats,
                "long_trades": len(long_records),
                "short_trades": len(short_records),
                "long_win_rate_pct": _summarize_trade_records(long_records, starting_balance)["win_rate_pct"],
                "short_win_rate_pct": _summarize_trade_records(short_records, starting_balance)["win_rate_pct"],
            },
            "series": _build_curve_series(pair_records, starting_balance),
        })

    pair_details.sort(
        key=lambda item: (
            -int(item["stats"].get("closed_trades") or 0),
            -float(item["stats"].get("net_profit_abs_usd") or 0.0),
            item["pair"],
        )
    )
    return pair_details


def _build_market_cards(active_pair_scores: dict) -> list[dict]:
    ranked_pairs = active_pair_scores.get("ranked_pairs", [])
    selected_pairs = set(active_pair_scores.get("selected_pairs", []))
    if not isinstance(ranked_pairs, list):
        return []

    cards = []
    for item in ranked_pairs[:10]:
        if not isinstance(item, dict):
            continue
        pair = item.get("pair")
        cards.append({
            "pair": pair,
            "asset": _pair_asset_label(pair),
            "symbol": item.get("symbol"),
            "last_price": _round(item.get("last_price"), 4),
            "abs_change_pct": _round(item.get("abs_change_pct"), 2),
            "intraday_range_pct": _round(item.get("intraday_range_pct"), 2),
            "quality_score_pct": _round(float(item.get("quality_score") or 0.0) * 100.0, 1),
            "selected": pair in selected_pairs,
        })
    return cards


def _build_pipeline_filter_details(active_pairs: list[str]) -> dict:
    snapshot = _load_json(PIPELINE_STAGE_SNAPSHOT_PATH)
    pair_map = snapshot.get("pairs", {})
    if not isinstance(pair_map, dict):
        return {"generated_at": None, "records": []}

    ordered_pairs = active_pairs or sorted(pair_map.keys())
    records: list[dict] = []
    for pair in ordered_pairs:
        payload = pair_map.get(pair)
        if not isinstance(payload, dict):
            continue
        selected = payload.get("selected", {})
        if not isinstance(selected, dict):
            selected = {}
        records.append({
            "pair": pair,
            "asset": _pair_asset_label(pair),
            "close": _round(payload.get("close"), 6),
            "side": selected.get("side") or payload.get("selected_side") or "none",
            "pipeline_pass": bool(selected.get("pipeline_pass")),
            "blocked_stage": selected.get("blocked_stage"),
            "blocked_reason": selected.get("blocked_reason"),
            "strategy_pass": bool(selected.get("strategy_pass")),
            "ml_pass": bool(selected.get("ml_pass")),
            "dl_pass": bool(selected.get("dl_pass")),
            "llm_pass": bool(selected.get("llm_pass")),
            "llm_signal": selected.get("llm_signal"),
            "ensemble_prob_pct": _round(float(selected.get("ensemble_prob") or 0.0) * 100.0, 2) if selected.get("ensemble_prob") is not None else None,
            "ml_prob_pct": _round(float(selected.get("ml_prob") or 0.0) * 100.0, 2) if selected.get("ml_prob") is not None else None,
            "dl_prob_pct": _round(float(selected.get("dl_prob") or 0.0) * 100.0, 2) if selected.get("dl_prob") is not None else None,
            "enter_tag": selected.get("enter_tag"),
        })
    return {
        "generated_at": snapshot.get("generated_at"),
        "records": records,
    }


def _build_dashboard_payload(
    records: list[dict],
    *,
    starting_balance: float,
    balance_summary: dict,
    open_positions: list[dict],
    active_pair_scores: dict,
    active_pairs: list[str],
    tuning_summary: dict,
) -> dict:
    overall = _summarize_trade_records(records, starting_balance)
    long_records = [record for record in records if record.get("side") == "long"]
    short_records = [record for record in records if record.get("side") == "short"]
    long_stats = _summarize_trade_records(long_records, starting_balance)
    short_stats = _summarize_trade_records(short_records, starting_balance)
    today_local = datetime.now(LOCAL_TIMEZONE).date()
    today_records = [
        record
        for record in records
        if (_to_local_datetime(record.get("close_date")) or _to_local_datetime(record.get("open_date")))
        and (_to_local_datetime(record.get("close_date")) or _to_local_datetime(record.get("open_date"))).date() == today_local
    ]
    today_stats = _summarize_trade_records(today_records, starting_balance)
    today_stats["date_label"] = today_local.isoformat()
    today_intraday = _build_curve_series(today_records, starting_balance)
    pair_details = _build_pair_details(records, starting_balance)

    return {
        "overview": {
            "total_win_rate_pct": overall["win_rate_pct"],
            "remaining_balance_usd": _round(balance_summary.get("current_total"), 4),
            "available_balance_usd": _round(balance_summary.get("available"), 4),
            "today_profit_abs_usd": today_stats["net_profit_abs_usd"],
            "today_roi_pct": today_stats["roi_pct"],
            "today_fees_abs_usd": today_stats["fees_abs_usd"],
            "today_closed_trades": today_stats["closed_trades"],
            "total_profit_abs_usd": overall["net_profit_abs_usd"],
            "total_roi_pct": overall["roi_pct"],
            "open_positions": len(open_positions),
            "active_pairs": len(active_pairs),
            "baseline_label": tuning_summary.get("label") if tuning_summary.get("active") else "전체 전적",
        },
        "performance": {
            "overall": overall,
            "long": long_stats,
            "short": short_stats,
        },
        "today": today_stats,
        "charts": {
            "integrated_curve": _build_curve_series(records, starting_balance),
            "long_curve": _build_curve_series(long_records, starting_balance),
            "short_curve": _build_curve_series(short_records, starting_balance),
            "daily_profit": _build_daily_profit_series(records, starting_balance),
            "today_intraday": today_intraday,
        },
        "pairs": {
            "detail": pair_details,
            "top_options": [item["pair"] for item in pair_details[:12]],
        },
        "market_cards": _build_market_cards(active_pair_scores),
        "pipeline_filter": _build_pipeline_filter_details(active_pairs),
    }


def _build_tp_sl_policy(config: dict, settings_state: dict) -> dict:
    settings = load_settings_env(SETTINGS_ENV_PATH)
    order_types = config.get("order_types", {})
    base_stoploss_pct = float(
        settings.get("AGGRESSIVE_BASE_STOPLOSS_PCT")
        or settings.get("DEFAULT_STOP_LOSS_PCT")
        or 2.5
    )
    stoploss_reentry_cooldown_minutes = int(
        float(settings.get("AGGRESSIVE_STOPLOSS_REENTRY_COOLDOWN_MINUTES") or 60)
    )
    pair_cooldown_minutes = int(float(settings.get("AGGRESSIVE_PAIR_COOLDOWN_MINUTES") or 12))
    recovery_arm_peak_pct = float(settings.get("AGGRESSIVE_RECOVERY_ARM_PEAK_PCT") or 1.2)
    recovery_failsafe_pct = float(settings.get("AGGRESSIVE_RECOVERY_FAILSAFE_PCT") or 2.4)
    recovery_reclaim_ratio = float(settings.get("AGGRESSIVE_RECOVERY_RECLAIM_RATIO") or 0.85) * 100.0
    recovery_reclaim_buffer_pct = float(settings.get("AGGRESSIVE_RECOVERY_RECLAIM_BUFFER_PCT") or 0.40)
    recovery_min_target_pct = float(settings.get("AGGRESSIVE_RECOVERY_MIN_TARGET_PCT") or 0.45)
    recovery_fee_per_side_pct = float(settings.get("AGGRESSIVE_RECOVERY_FEE_PER_SIDE_PCT") or 0.075)
    recovery_fee_buffer_pct = float(settings.get("AGGRESSIVE_RECOVERY_FEE_BUFFER_PCT") or 0.03)
    recovery_min_minutes_before_dca = int(
        float(settings.get("AGGRESSIVE_RECOVERY_MIN_MINUTES_BEFORE_DCA") or 4)
    )
    recovery_dca_spacing_minutes = int(float(settings.get("AGGRESSIVE_RECOVERY_DCA_SPACING_MINUTES") or 8))
    recovery_hold_minutes = int(float(settings.get("AGGRESSIVE_RECOVERY_MAX_HOLD_MINUTES") or 240))
    dca_level1_loss_pct = float(settings.get("AGGRESSIVE_DCA_LEVEL1_LOSS_PCT") or 1.1)
    dca_level2_loss_pct = float(settings.get("AGGRESSIVE_DCA_LEVEL2_LOSS_PCT") or 2.0)
    dca_level1_multiplier = float(settings.get("AGGRESSIVE_DCA_LEVEL1_MULTIPLIER") or 1.0)
    dca_level2_multiplier = float(settings.get("AGGRESSIVE_DCA_LEVEL2_MULTIPLIER") or 2.0)
    default_roi_schedule = _roi_schedule_for_leverage(2.0)
    return {
        "reward_risk_profile": "capital_preservation_with_recovery",
        "initial_take_profit_pct": default_roi_schedule[0]["target_pct"],
        "base_stoploss_pct": _round(base_stoploss_pct, 2),
        "exchange_stoploss_enabled": bool(order_types.get("stoploss_on_exchange", False)),
        "exchange_stoploss_interval_sec": int(order_types.get("stoploss_on_exchange_interval") or 0),
        "exchange_stoploss_price_type": order_types.get("stoploss_price_type"),
        "early_grace_minutes": 10,
        "use_exit_signal": True,
        "custom_exit_active": True,
        "pair_cooldown_minutes": pair_cooldown_minutes,
        "stoploss_reentry_cooldown_minutes": stoploss_reentry_cooldown_minutes,
        "recovery_mode_enabled": bool(float(settings.get("AGGRESSIVE_RECOVERY_MODE_ENABLED") or 1.0) >= 0.5),
        "recovery_arm_peak_pct": _round(recovery_arm_peak_pct, 2),
        "recovery_failsafe_pct": _round(recovery_failsafe_pct, 2),
        "recovery_reclaim_ratio_pct": _round(recovery_reclaim_ratio, 1),
        "recovery_reclaim_buffer_pct": _round(recovery_reclaim_buffer_pct, 2),
        "recovery_min_target_pct": _round(recovery_min_target_pct, 2),
        "recovery_fee_per_side_pct": _round(recovery_fee_per_side_pct, 3),
        "recovery_fee_buffer_pct": _round(recovery_fee_buffer_pct, 2),
        "recovery_target_floor_rule": "max(static_min_target, round_trip_fee_by_leverage + fee_buffer)",
        "recovery_min_minutes_before_dca": recovery_min_minutes_before_dca,
        "recovery_dca_spacing_minutes": recovery_dca_spacing_minutes,
        "recovery_max_hold_minutes": recovery_hold_minutes,
        "leverage_base_caps": [
            {"min_leverage": 3.0, "base_stoploss_pct": 2.8},
            {"min_leverage": 4.0, "base_stoploss_pct": 2.5},
            {"min_leverage": 5.0, "base_stoploss_pct": 2.3},
        ],
        "roi_schedule": default_roi_schedule,
        "roi_schedule_by_leverage": [
            {"min_leverage": min_leverage, "schedule": schedule}
            for min_leverage, schedule in LEVERAGE_ROI_PROFILES
        ],
        "profit_lock_schedule": _profit_lock_schedule_for_leverage(2.0),
        "profit_lock_schedule_by_leverage": [
            {"min_leverage": min_leverage, "schedule": schedule}
            for min_leverage, schedule in LEVERAGE_PROFIT_LOCK_PROFILES
        ],
        "recovery_dca_levels": [
            {"level": 1, "loss_pct": _round(dca_level1_loss_pct, 2), "stake_multiplier": _round(dca_level1_multiplier, 2)},
            {"level": 2, "loss_pct": _round(dca_level2_loss_pct, 2), "stake_multiplier": _round(dca_level2_multiplier, 2)},
        ],
        "stake_ratio_pct": _round(settings_state.get("stake_ratio_pct"), 4),
    }


def _build_automation_summary(config: dict) -> dict:
    freqai_config = config.get("freqai", {})
    identifier = freqai_config.get("identifier")
    model_dir = ROOT / "runtime" / "freqtrade" / "user_data" / "models" / str(identifier or "")
    pair_dictionary = _load_json(model_dir / "pair_dictionary.json") if identifier else {}
    latest_pair = None
    latest_timestamp = 0
    trained_pairs_count = 0

    if isinstance(pair_dictionary, dict):
        trained_pairs_count = len(pair_dictionary)
        for pair, payload in pair_dictionary.items():
            if not isinstance(payload, dict):
                continue
            trained_timestamp = int(payload.get("trained_timestamp") or 0)
            if trained_timestamp > latest_timestamp:
                latest_timestamp = trained_timestamp
                latest_pair = pair

    component_snapshot = _load_json(COMPONENT_SNAPSHOT_PATH)
    llm_snapshot = _load_json(LLM_SIGNAL_SNAPSHOT_PATH)
    component_pairs = component_snapshot.get("pairs", {})
    llm_signals = llm_snapshot.get("signals", {})

    return {
        "freqai_enabled": bool(freqai_config.get("enabled", False)),
        "live_retrain_hours": freqai_config.get("live_retrain_hours"),
        "train_period_days": freqai_config.get("train_period_days"),
        "identifier": identifier,
        "trained_pairs_count": trained_pairs_count,
        "latest_trained_pair": latest_pair,
        "latest_trained_at": (
            datetime.fromtimestamp(latest_timestamp, tz=timezone.utc).isoformat()
            if latest_timestamp
            else None
        ),
        "component_snapshot_generated_at": component_snapshot.get("generated_at"),
        "component_snapshot_pairs": len(component_pairs) if isinstance(component_pairs, dict) else 0,
        "llm_snapshot_generated_at": llm_snapshot.get("generated_at"),
        "llm_snapshot_pairs": len(llm_signals) if isinstance(llm_signals, dict) else 0,
        "auto_parameter_tuning_enabled": False,
        "tuning_mode": "manual_baseline_marker_only",
    }


def _fetch_api_json(config: dict, path: str) -> dict | list | None:
    api_config = config.get("api_server", {})
    if not api_config.get("enabled"):
        return None

    username = api_config.get("username", "")
    password = api_config.get("password", "")
    port = api_config.get("listen_port", 8080)
    address = api_config.get("listen_ip_address", "127.0.0.1")
    auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"http://{address}:{port}/api/v1{path}",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=2.5) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _extract_balance_summary(config: dict, api_balance: dict | None, wallet: float, realized_profit_abs: float, open_stake_total: float) -> dict:
    stake_currency = str(config.get("stake_currency", "USDT"))
    if api_balance:
        currencies = api_balance.get("currencies", [])
        stake_row = None
        for currency in currencies:
            if currency.get("currency") == stake_currency and not currency.get("is_position"):
                stake_row = currency
                break
        current_total = api_balance.get("value_bot") or api_balance.get("total_bot") or api_balance.get("value") or api_balance.get("total")
        if stake_row:
            return {
                "source": "freqtrade_api",
                "currency": stake_currency,
                "current_total": _round(current_total, 4),
                "available": _round(stake_row.get("free"), 4),
                "used": _round(stake_row.get("used"), 4),
                "starting_balance": _round(wallet, 4),
            }

    estimated_total = wallet + realized_profit_abs
    estimated_used = min(open_stake_total, estimated_total) if estimated_total > 0 else 0.0
    estimated_available = max(estimated_total - estimated_used, 0.0)
    return {
        "source": "estimated",
        "currency": stake_currency,
        "current_total": _round(estimated_total, 4),
        "available": _round(estimated_available, 4),
        "used": _round(estimated_used, 4),
        "starting_balance": _round(wallet, 4),
    }


def _resolve_starting_balance(balance_summary: dict, settings_state: dict, wallet: float) -> tuple[float, dict]:
    if not bool(settings_state.get("live_trading_enabled", False)):
        balance_summary["starting_balance"] = _round(wallet, 4)
        balance_summary["starting_balance_source"] = "dry_run_wallet"
        return float(wallet), {}

    live_state = _load_json(LIVE_ACCOUNT_STATE_PATH)
    current_total = balance_summary.get("current_total")
    if current_total is None:
        starting_balance = float(live_state.get("starting_balance") or wallet)
        balance_summary["starting_balance"] = _round(starting_balance, 4)
        balance_summary["starting_balance_source"] = live_state.get("source", "fallback_wallet")
        balance_summary["live_session_started_at"] = live_state.get("started_at")
        return starting_balance, live_state

    if not live_state or live_state.get("starting_balance") is None:
        live_state = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "starting_balance": float(current_total),
            "currency": balance_summary.get("currency", "USDT"),
            "source": balance_summary.get("source", "live_snapshot"),
        }
        _write_json(LIVE_ACCOUNT_STATE_PATH, live_state)

    starting_balance = float(live_state.get("starting_balance") or current_total)
    balance_summary["starting_balance"] = _round(starting_balance, 4)
    balance_summary["starting_balance_source"] = live_state.get("source", "live_snapshot")
    balance_summary["live_session_started_at"] = live_state.get("started_at")
    return starting_balance, live_state


def _build_mode_summary(config: dict, settings_state: dict) -> dict:
    mode = settings_state.get("mode")
    if not mode:
        mode = "dry_run" if config.get("dry_run", True) else "live"
    return {
        "mode": mode,
        "dry_run": bool(config.get("dry_run", True)),
        "api_keys_present": bool(settings_state.get("api_keys_present", False)),
        "live_requested": bool(settings_state.get("live_requested", False)),
        "order_submission_enabled": bool(settings_state.get("order_submission_enabled", False)),
        "live_preflight_enabled": bool(settings_state.get("live_preflight_enabled", False)),
        "live_trading_enabled": bool(settings_state.get("live_trading_enabled", False)),
        "api_key_masked": settings_state.get("api_key_masked", ""),
        "anthropic_key_present": bool(settings_state.get("anthropic_key_present", False)),
    }


def _base_status(config: dict, settings_state: dict, live_preflight: dict, trade_shadow: dict, resolved_pairs: list[str], active_pairs: list[str]) -> dict:
    wallet = float(config.get("dry_run_wallet", 0) or 0)
    tp_sl_policy = _build_tp_sl_policy(config, settings_state)
    volume_pairlist = next((p for p in config.get("pairlists", []) if p.get("method") == "VolumePairList"), None)
    downloaded_pairs = sorted({p.name.split("-")[0].replace("_USDT_USDT", "/USDT:USDT") for p in DATA_DIR.glob("*-3m-futures.feather")})
    active_pair_scores = _load_active_pair_scores()
    balance_summary = {
        "source": "unavailable",
        "currency": str(config.get("stake_currency", "USDT")),
        "current_total": _round(wallet, 4),
        "available": _round(wallet, 4),
        "used": 0.0,
        "starting_balance": _round(wallet, 4),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bot_name": config.get("bot_name"),
        "engine": _build_engine_summary(config, settings_state),
        "mode": _build_mode_summary(config, settings_state),
        "live_preflight": live_preflight,
        "trade_shadow": trade_shadow,
        "actual_binance_account": {
            "available_balance": None,
            "total_wallet_balance": None,
            "total_margin_balance": None,
            "positions_count": 0,
            "dynamic_stake": None,
            "stake_ratio_pct": _round(settings_state.get("stake_ratio_pct"), 4),
        },
        "balance": balance_summary,
        "live_account_state": {},
        "dry_run_wallet": wallet,
        "stake_amount": config.get("stake_amount"),
        "stake_mode": "dynamic_available_balance_pct",
        "stake_ratio_pct": settings_state.get("stake_ratio_pct", 10),
        "stake_note": "new entries use the configured percentage of currently available balance and skip below minimum stake",
        "max_open_trades": config.get("max_open_trades"),
        "timeframe": config.get("timeframe"),
        "tracked_pairs_mode": "volume_pairlist" if volume_pairlist else "static",
        "tracked_pairs_target": volume_pairlist.get("number_assets") if volume_pairlist else len(config.get("exchange", {}).get("pair_whitelist", [])),
        "tracked_pairs_resolved": len(resolved_pairs),
        "active_pairs_count": len(active_pairs),
        "tracked_pairs_observed": len(downloaded_pairs),
        "tracked_pairs": (active_pairs or resolved_pairs or downloaded_pairs)[:200],
        "active_universe": {
            "selection_source": active_pair_scores.get("selection_source"),
            "thresholds": active_pair_scores.get("thresholds", {}),
        },
        "tp_sl_policy": tp_sl_policy,
        "automation": _build_automation_summary(config),
        "pipeline": _build_pipeline_summary(active_pairs),
        "tuning": _empty_tuning_summary(),
        "stats": {
            "total_trades": 0,
            "open_trades": 0,
            "closed_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "gross_profit_abs_usd": 0.0,
            "fees_paid_usd": 0.0,
            "profit_abs_usd": 0.0,
            "gross_roi_pct": 0.0,
            "roi_pct": 0.0,
            "profit_factor": 0.0,
            "equity_delta_abs_usd": 0.0,
            "equity_roi_pct": 0.0,
            "current_balance_usd": balance_summary["current_total"],
            "available_balance_usd": balance_summary["available"],
            "used_balance_usd": balance_summary["used"],
        },
        "dashboard": _build_dashboard_payload(
            [],
            starting_balance=float(balance_summary["starting_balance"] or wallet),
            balance_summary=balance_summary,
            open_positions=[],
            active_pair_scores=active_pair_scores,
            active_pairs=active_pairs,
            tuning_summary=_empty_tuning_summary(),
        ),
        "open_positions": [],
        "live_positions": [],
        "stale_db_open_positions": [],
        "recent_closed": [],
        "pair_stats": [],
    }


def build_status() -> dict:
    config = _load_config()
    settings_state = _load_json(SETTINGS_STATE_PATH)
    tp_sl_policy = _build_tp_sl_policy(config, settings_state)
    live_preflight = _load_json(LIVE_PREFLIGHT_PATH)
    trade_shadow = _load_json(TRADE_SHADOW_PATH)
    resolved_pairs = _load_resolved_pairs()
    active_pairs = _load_active_pairs()
    db_path = _resolve_db_path()
    if not db_path.exists():
        return _base_status(config, settings_state, live_preflight, trade_shadow, resolved_pairs, active_pairs)
    wallet = float(config.get("dry_run_wallet", 0) or 0)

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("select 1 from trades limit 1")
    except sqlite3.OperationalError:
        try:
            conn.close()
        except Exception:
            pass
        return _base_status(config, settings_state, live_preflight, trade_shadow, resolved_pairs, active_pairs)

    total = _safe_fetchone(cur, "select count(*) from trades")
    open_count = _safe_fetchone(cur, "select count(*) from trades where is_open = 1")
    closed = _safe_fetchone(cur, "select count(*) from trades where is_open = 0")
    wins = _safe_fetchone(cur, "select count(*) from trades where is_open = 0 and coalesce(close_profit_abs, 0) > 0")
    losses = _safe_fetchone(cur, "select count(*) from trades where is_open = 0 and coalesce(close_profit_abs, 0) < 0")
    profit_abs = float(_safe_fetchone(cur, "select coalesce(sum(close_profit_abs), 0) from trades where is_open = 0", 0.0))
    fees_paid_abs = float(_safe_fetchone(cur, """
            select coalesce(sum(coalesce(fee_open_cost, 0) + coalesce(fee_close_cost, 0) + coalesce(funding_fees, 0)), 0)
            from trades
            where is_open = 0
            """, 0.0))
    gross_profit_abs = profit_abs + fees_paid_abs
    gross_win = float(_safe_fetchone(cur, "select coalesce(sum(close_profit_abs), 0) from trades where is_open = 0 and coalesce(close_profit_abs, 0) > 0", 0.0))
    gross_loss = float(_safe_fetchone(cur, "select coalesce(sum(close_profit_abs), 0) from trades where is_open = 0 and coalesce(close_profit_abs, 0) < 0", 0.0))
    open_stake_total = float(_safe_fetchone(cur, "select coalesce(sum(stake_amount), 0) from trades where is_open = 1", 0.0))
    win_rate = (wins / closed * 100.0) if closed else 0.0
    profit_factor = (gross_win / abs(gross_loss)) if gross_loss < 0 else (gross_win if gross_win > 0 else 0.0)

    api_balance = _fetch_api_json(config, "/balance")
    api_status = _fetch_api_json(config, "/status")
    api_status_map: dict[int, dict] = {}
    if isinstance(api_status, list):
        for item in api_status:
            trade_id = item.get("trade_id")
            if isinstance(trade_id, int):
                api_status_map[trade_id] = item

    balance_summary = _extract_balance_summary(config, api_balance if isinstance(api_balance, dict) else None, wallet, profit_abs, open_stake_total)
    starting_balance, live_account_state = _resolve_starting_balance(balance_summary, settings_state, wallet)
    roi_pct = (profit_abs / starting_balance * 100.0) if starting_balance else 0.0
    gross_roi_pct = (gross_profit_abs / starting_balance * 100.0) if starting_balance else 0.0
    current_total = balance_summary.get("current_total")
    equity_delta_abs = (float(current_total) - float(starting_balance)) if current_total is not None and starting_balance else None
    equity_roi_pct = ((equity_delta_abs / float(starting_balance)) * 100.0) if equity_delta_abs is not None and starting_balance else None

    account_check = live_preflight.get("checks", {}).get("account", {}) if isinstance(live_preflight, dict) else {}
    usdt_check = live_preflight.get("checks", {}).get("usdt_balance", {}) if isinstance(live_preflight, dict) else {}
    actual_binance_account = {
        "available_balance": _round(account_check.get("available_balance"), 8),
        "total_wallet_balance": _round(account_check.get("total_wallet_balance"), 8),
        "total_margin_balance": _round(account_check.get("total_margin_balance"), 8),
        "positions_count": int(account_check.get("positions_count") or 0),
        "dynamic_stake": _round(usdt_check.get("dynamic_stake"), 8),
        "stake_ratio_pct": _round(usdt_check.get("stake_ratio_pct"), 4),
    }
    actual_positions_raw = trade_shadow.get("actual_positions", []) if isinstance(trade_shadow, dict) else []
    if not isinstance(actual_positions_raw, list):
        actual_positions_raw = []
    actual_positions_map: dict[str, dict] = {}
    for item in actual_positions_raw:
        if not isinstance(item, dict):
            continue
        pair = _symbol_to_pair(item.get("symbol"))
        if not pair:
            continue
        try:
            position_amt = float(item.get("positionAmt", 0) or 0.0)
        except (TypeError, ValueError):
            position_amt = 0.0
        if abs(position_amt) <= 0:
            continue
        actual_positions_map[pair] = {
            "pair": pair,
            "symbol": item.get("symbol"),
            "position_amt": position_amt,
            "side": "long" if position_amt > 0 else "short",
            "entry_price": _round(item.get("entryPrice"), 6),
            "mark_price": _round(item.get("markPrice"), 6),
            "unrealized_profit_abs": _round(item.get("unRealizedProfit"), 4),
            "leverage": _round(item.get("leverage"), 2),
            "position_side": item.get("positionSide"),
        }

    tuning_summary = _build_tuning_summary(cur)
    visible_baseline_trade_id = int(tuning_summary.get("baseline_trade_id") or 0) if tuning_summary.get("active") else 0
    open_trade_ids = [int(row["id"]) for row in cur.execute("select id from trades where is_open = 1").fetchall()]
    trade_custom_data_map = _load_trade_custom_data_map(cur, open_trade_ids)
    roi_schedule = tp_sl_policy.get("roi_schedule", [])
    now_utc = datetime.now(timezone.utc)

    open_positions = []
    for row in cur.execute("""
        select id, pair, open_date, open_rate, stake_amount, leverage, is_short, enter_tag,
               fee_open_cost, funding_fee_running, amount
        from trades
        where is_open = 1
        order by open_date desc
        """):
        api_item = api_status_map.get(int(row["id"]), {})
        trade_custom = trade_custom_data_map.get(int(row["id"]), {})
        fee_paid = float(row["fee_open_cost"] or 0.0) + float(api_item.get("funding_fees") or row["funding_fee_running"] or 0.0)
        current_net_profit = api_item.get("profit_abs")
        if current_net_profit is None:
            current_net_profit = api_item.get("total_profit_abs")
        current_roi_pct = api_item.get("profit_pct")
        if current_roi_pct is None and api_item.get("profit_ratio") is not None:
            current_roi_pct = float(api_item["profit_ratio"]) * 100.0
        elif current_roi_pct is not None:
            current_roi_pct = float(current_roi_pct)
        current_gross_profit = (float(current_net_profit) + fee_paid) if current_net_profit is not None else None
        leverage_value = float(row["leverage"] or 1.0)
        base_tp_target_pct = _current_roi_target_pct(
            row["open_date"],
            _roi_schedule_for_leverage(leverage_value),
            now_utc=now_utc,
        )
        recovery_peak_profit = trade_custom.get("recovery_peak_profit")
        recovery_target_profit = trade_custom.get("recovery_target_profit")
        recovery_peak_profit_pct = _round(float(recovery_peak_profit) * 100.0, 4) if recovery_peak_profit is not None else None
        recovery_target_profit_pct = _round(float(recovery_target_profit) * 100.0, 4) if recovery_target_profit is not None else None
        recovery_armed = bool(trade_custom.get("recovery_mode_armed", False))
        recovery_tp_target_pct = (
            recovery_target_profit_pct
            if recovery_armed and recovery_target_profit_pct is not None and recovery_target_profit_pct > 0
            else None
        )
        effective_tp_target_pct = recovery_tp_target_pct if recovery_tp_target_pct is not None else base_tp_target_pct
        recovery_dca_count = int(trade_custom.get("recovery_dca_count") or max(int(api_item.get("nr_of_successful_entries") or 1) - 1, 0))
        recovery_last_adjustment_tag = trade_custom.get("recovery_last_adjustment_tag")
        recovery_parts: list[str] = []
        if recovery_armed:
            recovery_parts.append("armed")
        elif recovery_peak_profit_pct is not None and recovery_peak_profit_pct > 0:
            recovery_parts.append("tracking")
        if recovery_peak_profit_pct is not None and recovery_peak_profit_pct > 0:
            recovery_parts.append(f"peak {recovery_peak_profit_pct:.2f}%")
        if recovery_armed and recovery_target_profit_pct is not None and recovery_target_profit_pct > 0:
            recovery_parts.append(f"target {recovery_target_profit_pct:.2f}%")
        if recovery_armed or recovery_dca_count > 0 or (recovery_peak_profit_pct is not None and recovery_peak_profit_pct > 0):
            recovery_parts.append(f"dca {recovery_dca_count}")
        if recovery_last_adjustment_tag:
            recovery_parts.append(str(recovery_last_adjustment_tag))
        pair = str(row["pair"])
        exchange_position = actual_positions_map.get(pair)
        exchange_verified = exchange_position is not None
        open_positions.append({
            "id": row["id"],
            "pair": pair,
            "open_date": row["open_date"],
            "open_rate": _round(row["open_rate"], 6),
            "current_rate": _round(api_item.get("current_rate"), 6),
            "stake_amount": _round(row["stake_amount"], 4),
            "leverage": _round(leverage_value, 2),
            "side": "short" if row["is_short"] else "long",
            "enter_tag": row["enter_tag"],
            "gross_profit_abs": _round(current_gross_profit, 4),
            "fee_paid_abs": _round(fee_paid, 4),
            "net_profit_abs": _round(current_net_profit, 4),
            "roi_pct": _round(current_roi_pct, 4),
            "base_tp_target_pct": base_tp_target_pct,
            "recovery_tp_target_pct": recovery_tp_target_pct,
            "effective_tp_target_pct": effective_tp_target_pct,
            "tp_mode": "recovery" if recovery_tp_target_pct is not None else "base",
            "recovery_armed": recovery_armed,
            "recovery_peak_profit_pct": recovery_peak_profit_pct,
            "recovery_target_profit_pct": recovery_target_profit_pct,
            "recovery_dca_count": recovery_dca_count,
            "recovery_last_adjustment_tag": recovery_last_adjustment_tag,
            "recovery_summary": " / ".join(part for part in recovery_parts if part) if recovery_parts else "-",
            "exchange_verified": exchange_verified,
            "exchange_symbol": exchange_position.get("symbol") if exchange_position else _pair_to_symbol(pair),
        })

    live_positions = []
    stale_db_open_positions = []
    db_open_position_map = {str(item.get("pair")): item for item in open_positions if item.get("pair")}
    for position in open_positions:
        pair = str(position.get("pair") or "")
        exchange_position = actual_positions_map.get(pair)
        if exchange_position is None:
            stale_db_open_positions.append({
                "id": position.get("id"),
                "pair": pair,
                "enter_tag": position.get("enter_tag"),
            })
            continue
        live_position = dict(position)
        live_position["current_rate"] = exchange_position.get("mark_price") or live_position.get("current_rate")
        live_position["side"] = exchange_position.get("side") or live_position.get("side")
        live_position["exchange_verified"] = True
        live_position["exchange_symbol"] = exchange_position.get("symbol")
        unrealized_profit_abs = exchange_position.get("unrealized_profit_abs")
        if unrealized_profit_abs is not None:
            live_position["net_profit_abs"] = unrealized_profit_abs
            stake_amount = float(live_position.get("stake_amount") or 0.0)
            live_position["roi_pct"] = _round((unrealized_profit_abs / stake_amount * 100.0), 4) if stake_amount > 0 else live_position.get("roi_pct")
        live_positions.append(live_position)

    for pair, exchange_position in actual_positions_map.items():
        if pair in db_open_position_map:
            continue
        entry_price = exchange_position.get("entry_price")
        leverage_value = float(exchange_position.get("leverage") or 1.0)
        position_amt = abs(float(exchange_position.get("position_amt") or 0.0))
        stake_amount = None
        if entry_price is not None and leverage_value > 0:
            stake_amount = (position_amt * float(entry_price)) / leverage_value
        base_tp_target_pct = _current_roi_target_pct(
            None,
            _roi_schedule_for_leverage(leverage_value),
            now_utc=now_utc,
        )
        unrealized_profit_abs = exchange_position.get("unrealized_profit_abs")
        live_positions.append({
            "id": None,
            "pair": pair,
            "open_date": None,
            "open_rate": entry_price,
            "current_rate": exchange_position.get("mark_price"),
            "stake_amount": _round(stake_amount, 4),
            "leverage": _round(leverage_value, 2),
            "side": exchange_position.get("side"),
            "enter_tag": "actual_exchange_only",
            "gross_profit_abs": unrealized_profit_abs,
            "fee_paid_abs": None,
            "net_profit_abs": unrealized_profit_abs,
            "roi_pct": _round((float(unrealized_profit_abs) / stake_amount * 100.0), 4) if unrealized_profit_abs is not None and stake_amount else None,
            "base_tp_target_pct": base_tp_target_pct,
            "recovery_tp_target_pct": None,
            "effective_tp_target_pct": base_tp_target_pct,
            "tp_mode": "base",
            "recovery_armed": False,
            "recovery_peak_profit_pct": None,
            "recovery_target_profit_pct": None,
            "recovery_dca_count": 0,
            "recovery_last_adjustment_tag": None,
            "recovery_summary": "-",
            "exchange_verified": True,
            "exchange_symbol": exchange_position.get("symbol"),
        })

    closed_records = []
    closed_rows = cur.execute("""
        select id, pair, open_date, close_date, open_rate, close_rate, close_profit_abs, close_profit,
               exit_reason, leverage, is_short, enter_tag, stake_amount, max_rate, min_rate,
               fee_open_cost, fee_close_cost, funding_fees
        from trades
        where is_open = 0 and id > ?
        order by close_date desc
        """, (visible_baseline_trade_id,)).fetchall()

    for row in closed_rows:
        total_fees = float(row["fee_open_cost"] or 0.0) + float(row["fee_close_cost"] or 0.0) + float(row["funding_fees"] or 0.0)
        net_profit_abs = float(row["close_profit_abs"] or 0.0)
        gross_profit_row = net_profit_abs + total_fees
        max_tp_pct, max_sl_pct = _compute_excursion_pcts(
            row["open_rate"],
            row["max_rate"],
            row["min_rate"],
            is_short=bool(row["is_short"]),
            leverage=row["leverage"],
        )
        closed_records.append({
            "id": row["id"],
            "pair": row["pair"],
            "open_date": row["open_date"],
            "close_date": row["close_date"],
            "open_rate": _round(row["open_rate"], 6),
            "close_rate": _round(row["close_rate"], 6),
            "stake_amount": _round(row["stake_amount"], 4),
            "gross_profit_abs": _round(gross_profit_row, 4),
            "fee_total_abs": _round(total_fees, 4),
            "net_profit_abs": _round(net_profit_abs, 4),
            "profit_pct": _round((row["close_profit"] or 0.0) * 100.0, 4),
            "max_tp_pct": _round(max_tp_pct, 4),
            "max_sl_pct": _round(max_sl_pct, 4),
            "exit_reason": row["exit_reason"],
            "leverage": _round(row["leverage"], 2),
            "side": "short" if row["is_short"] else "long",
            "enter_tag": row["enter_tag"],
        })

    recent_closed = closed_records[:25]

    pair_buckets: dict[str, dict] = {}
    for record in closed_records:
        pair = record["pair"]
        bucket = pair_buckets.setdefault(
            pair,
            {
                "pair": pair,
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "net_profit_abs": 0.0,
                "fees_abs": 0.0,
                "avg_profit_sum": 0.0,
                "avg_max_tp_sum": 0.0,
                "avg_max_sl_sum": 0.0,
                "excursion_count": 0,
                "best_max_tp_pct": None,
                "worst_max_sl_pct": None,
            },
        )
        close_profit_abs = float(record["net_profit_abs"] or 0.0)
        fees_abs = float(record["fee_total_abs"] or 0.0)
        avg_profit_pct = float(record["profit_pct"] or 0.0)
        max_tp_pct = record["max_tp_pct"]
        max_sl_pct = record["max_sl_pct"]

        bucket["trades"] += 1
        bucket["wins"] += 1 if close_profit_abs > 0 else 0
        bucket["losses"] += 1 if close_profit_abs < 0 else 0
        bucket["net_profit_abs"] += close_profit_abs
        bucket["fees_abs"] += fees_abs
        bucket["avg_profit_sum"] += avg_profit_pct
        if max_tp_pct is not None:
            bucket["avg_max_tp_sum"] += max_tp_pct
            current_best_tp = bucket["best_max_tp_pct"]
            bucket["best_max_tp_pct"] = max_tp_pct if current_best_tp is None else max(current_best_tp, max_tp_pct)
        if max_sl_pct is not None:
            bucket["avg_max_sl_sum"] += max_sl_pct
            current_worst_sl = bucket["worst_max_sl_pct"]
            bucket["worst_max_sl_pct"] = max_sl_pct if current_worst_sl is None else min(current_worst_sl, max_sl_pct)
        if max_tp_pct is not None or max_sl_pct is not None:
            bucket["excursion_count"] += 1

    pair_stats = []
    for bucket in sorted(pair_buckets.values(), key=lambda item: item["net_profit_abs"], reverse=True)[:20]:
        trades = int(bucket["trades"])
        excursion_count = int(bucket["excursion_count"])
        pair_stats.append({
            "pair": bucket["pair"],
            "trades": trades,
            "wins": int(bucket["wins"]),
            "losses": int(bucket["losses"]),
            "win_rate": _round((bucket["wins"] / trades * 100.0) if trades else 0.0, 2),
            "net_profit_abs": _round(bucket["net_profit_abs"], 4),
            "fees_abs": _round(bucket["fees_abs"], 4),
            "avg_profit_pct": _round((bucket["avg_profit_sum"] / trades) if trades else 0.0, 4),
            "avg_max_tp_pct": _round((bucket["avg_max_tp_sum"] / excursion_count) if excursion_count else None, 4),
            "avg_max_sl_pct": _round((bucket["avg_max_sl_sum"] / excursion_count) if excursion_count else None, 4),
            "best_max_tp_pct": _round(bucket["best_max_tp_pct"], 4),
            "worst_max_sl_pct": _round(bucket["worst_max_sl_pct"], 4),
        })

    downloaded_pairs = sorted({p.name.split("-")[0].replace("_USDT_USDT", "/USDT:USDT") for p in DATA_DIR.glob("*-3m-futures.feather")})
    pairlists = config.get("pairlists", [])
    volume_pairlist = next((p for p in pairlists if p.get("method") == "VolumePairList"), None)
    active_pair_scores = _load_active_pair_scores()
    dashboard = _build_dashboard_payload(
        closed_records,
        starting_balance=starting_balance,
        balance_summary=balance_summary,
        open_positions=live_positions,
        active_pair_scores=active_pair_scores,
        active_pairs=active_pairs,
        tuning_summary=tuning_summary,
    )
    conn.close()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bot_name": config.get("bot_name"),
        "engine": _build_engine_summary(config, settings_state),
        "mode": _build_mode_summary(config, settings_state),
        "live_preflight": live_preflight,
        "trade_shadow": trade_shadow,
        "actual_binance_account": actual_binance_account,
        "balance": balance_summary,
        "live_account_state": live_account_state,
        "dry_run_wallet": wallet,
        "stake_amount": config.get("stake_amount"),
        "stake_mode": "dynamic_available_balance_pct",
        "stake_ratio_pct": settings_state.get("stake_ratio_pct", 10),
        "stake_note": "new entries use the configured percentage of currently available balance and skip below minimum stake",
        "max_open_trades": config.get("max_open_trades"),
        "timeframe": config.get("timeframe"),
        "tracked_pairs_mode": "volume_pairlist" if volume_pairlist else "static",
        "tracked_pairs_target": volume_pairlist.get("number_assets") if volume_pairlist else len(config.get("exchange", {}).get("pair_whitelist", [])),
        "tracked_pairs_resolved": len(resolved_pairs),
        "active_pairs_count": len(active_pairs),
        "tracked_pairs_observed": len(downloaded_pairs),
        "tracked_pairs": (active_pairs or resolved_pairs or downloaded_pairs)[:200],
        "active_universe": {
            "selection_source": active_pair_scores.get("selection_source"),
            "thresholds": active_pair_scores.get("thresholds", {}),
        },
        "tp_sl_policy": tp_sl_policy,
        "automation": _build_automation_summary(config),
        "pipeline": _build_pipeline_summary(active_pairs),
        "tuning": tuning_summary,
        "stats": {
            "total_trades": total,
            "open_trades": open_count,
            "closed_trades": closed,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": _round(win_rate, 2),
            "gross_profit_abs_usd": _round(gross_profit_abs, 4),
            "fees_paid_usd": _round(fees_paid_abs, 4),
            "profit_abs_usd": _round(profit_abs, 4),
            "gross_roi_pct": _round(gross_roi_pct, 4),
            "roi_pct": _round(roi_pct, 4),
            "profit_factor": _round(profit_factor, 4),
            "equity_delta_abs_usd": _round(equity_delta_abs, 4),
            "equity_roi_pct": _round(equity_roi_pct, 4),
            "current_balance_usd": balance_summary["current_total"],
            "available_balance_usd": balance_summary["available"],
            "used_balance_usd": balance_summary["used"],
        },
        "visible_stats": {
            "total_trades": tuning_summary["stats_since_tuning"]["total_trades"] if tuning_summary.get("active") else total,
            "open_trades": tuning_summary["stats_since_tuning"]["open_trades"] if tuning_summary.get("active") else open_count,
            "closed_trades": tuning_summary["stats_since_tuning"]["closed_trades"] if tuning_summary.get("active") else closed,
            "wins": tuning_summary["stats_since_tuning"]["wins"] if tuning_summary.get("active") else wins,
            "losses": tuning_summary["stats_since_tuning"]["losses"] if tuning_summary.get("active") else losses,
            "win_rate_pct": tuning_summary["stats_since_tuning"]["win_rate_pct"] if tuning_summary.get("active") else _round(win_rate, 2),
            "gross_profit_abs_usd": tuning_summary["stats_since_tuning"]["gross_profit_abs_usd"] if tuning_summary.get("active") else _round(gross_profit_abs, 4),
            "fees_paid_usd": tuning_summary["stats_since_tuning"]["fees_paid_usd"] if tuning_summary.get("active") else _round(fees_paid_abs, 4),
            "profit_abs_usd": tuning_summary["stats_since_tuning"]["profit_abs_usd"] if tuning_summary.get("active") else _round(profit_abs, 4),
            "profit_factor": tuning_summary["stats_since_tuning"]["profit_factor"] if tuning_summary.get("active") else _round(profit_factor, 4),
            "current_balance_usd": balance_summary["current_total"],
            "available_balance_usd": balance_summary["available"],
            "used_balance_usd": balance_summary["used"],
            "carryover_open_trades": tuning_summary.get("carryover_open_trades_count", 0) if tuning_summary.get("active") else 0,
        },
        "dashboard": dashboard,
        "open_positions": open_positions,
        "live_positions": live_positions,
        "stale_db_open_positions": stale_db_open_positions,
        "recent_closed": recent_closed,
        "pair_stats": pair_stats,
    }


def main() -> None:
    status = build_status()
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
