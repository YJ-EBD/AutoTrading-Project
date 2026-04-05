from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import talib.abstract as ta
from pandas import DataFrame
from technical import qtpylib

from freqtrade.persistence import Trade

from trade.dynamic_stake_freqai_strategy import DynamicStakeFreqaiStrategy
from trade.llm_signal_bridge import llm_signal_for_pair

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_STAGE_SNAPSHOT_PATH = ROOT / "runtime" / "pipeline_stage_snapshot.json"
COMPONENT_SNAPSHOT_PATH = ROOT / "runtime" / "freqai_component_snapshot.json"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        numeric = float(value)
        if np.isnan(numeric):
            return default
        return numeric
    except (TypeError, ValueError):
        return default


def _utc_now_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp_path.replace(path)


class AggressiveDynamicFreqaiStrategy(DynamicStakeFreqaiStrategy):
    minimal_roi = {"0": 0.08}
    stoploss = -0.025
    use_custom_stoploss = True
    use_custom_roi = True
    use_exit_signal = True
    position_adjustment_enable = True
    max_entry_position_adjustment = 2
    process_only_new_candles = True
    startup_candle_count = 240
    can_short = True
    stake_ratio = 0.10
    stage_probability_threshold = _env_float("AGGRESSIVE_STAGE_PROBABILITY_THRESHOLD", 0.54)
    entry_adx_min = _env_float("AGGRESSIVE_ENTRY_ADX_MIN", 13.0)
    entry_rel_volume_min = _env_float("AGGRESSIVE_ENTRY_REL_VOLUME_MIN", 0.50)
    entry_high_conf_rel_volume_min = _env_float("AGGRESSIVE_HIGH_CONF_REL_VOLUME_MIN", 0.35)
    entry_breakout_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_BREAKOUT_TOLERANCE_PCT", 0.005)
    entry_fast_ema_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_FAST_EMA_TOLERANCE_PCT", 0.001)
    entry_ema_stack_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_EMA_STACK_TOLERANCE_PCT", 0.0005)
    entry_ema200_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_EMA200_TOLERANCE_PCT", 0.002)
    entry_max_ema_distance_pct = _env_float("AGGRESSIVE_ENTRY_MAX_EMA_DISTANCE_PCT", 0.04)
    high_confidence_threshold = _env_float("AGGRESSIVE_HIGH_CONFIDENCE_THRESHOLD", 0.72)
    base_stoploss_pct = _env_float("AGGRESSIVE_BASE_STOPLOSS_PCT", 0.025)
    max_live_leverage = _env_float("AGGRESSIVE_MAX_LEVERAGE", 3.0)
    recovery_mode_enabled = _env_float("AGGRESSIVE_RECOVERY_MODE_ENABLED", 1.0) >= 0.5
    recovery_arm_peak_profit_pct = abs(_env_float("AGGRESSIVE_RECOVERY_ARM_PEAK_PCT", 1.2)) / 100.0
    recovery_activation_negative_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_NEGATIVE_ACTIVATION_PCT", 0.15)
    ) / 100.0
    recovery_reclaim_ratio = max(
        0.55,
        min(_env_float("AGGRESSIVE_RECOVERY_RECLAIM_RATIO", 0.85), 0.99),
    )
    recovery_reclaim_buffer_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_RECLAIM_BUFFER_PCT", 0.40)
    ) / 100.0
    recovery_min_target_pct = abs(_env_float("AGGRESSIVE_RECOVERY_MIN_TARGET_PCT", 0.45)) / 100.0
    recovery_failsafe_pct = abs(_env_float("AGGRESSIVE_RECOVERY_FAILSAFE_PCT", 2.4)) / 100.0
    recovery_max_hold_minutes = max(
        60,
        int(_env_float("AGGRESSIVE_RECOVERY_MAX_HOLD_MINUTES", 240)),
    )
    recovery_min_minutes_before_dca = max(
        1,
        int(_env_float("AGGRESSIVE_RECOVERY_MIN_MINUTES_BEFORE_DCA", 4)),
    )
    recovery_dca_spacing_minutes = max(
        1,
        int(_env_float("AGGRESSIVE_RECOVERY_DCA_SPACING_MINUTES", 8)),
    )
    dca_level1_loss_pct = abs(_env_float("AGGRESSIVE_DCA_LEVEL1_LOSS_PCT", 1.1)) / 100.0
    dca_level2_loss_pct = abs(_env_float("AGGRESSIVE_DCA_LEVEL2_LOSS_PCT", 2.0)) / 100.0
    dca_level1_multiplier = max(0.5, min(_env_float("AGGRESSIVE_DCA_LEVEL1_MULTIPLIER", 1.0), 1.5))
    dca_level2_multiplier = max(1.0, min(_env_float("AGGRESSIVE_DCA_LEVEL2_MULTIPLIER", 2.0), 2.5))
    stoploss_reentry_cooldown_minutes = max(
        30,
        min(int(_env_float("AGGRESSIVE_STOPLOSS_REENTRY_COOLDOWN_MINUTES", 60.0)), 90),
    )
    pair_cooldown_minutes = max(
        5,
        min(int(_env_float("AGGRESSIVE_PAIR_COOLDOWN_MINUTES", 12.0)), 30),
    )

    order_types = {
        "entry": "limit",
        "exit": "market",
        "force_entry": "market",
        "force_exit": "market",
        "emergency_exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": True,
        "stoploss_on_exchange_interval": 30,
        "stoploss_price_type": "mark",
    }

    order_time_in_force = {"entry": "GTC", "exit": "GTC"}

    def version(self) -> str:
        return "aggressive-v1.7"

    @property
    def protections(self) -> list[dict]:
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration": self.pair_cooldown_minutes,
            },
            {
                "method": "StoplossGuard",
                "lookback_period": self.stoploss_reentry_cooldown_minutes,
                "stop_duration": self.stoploss_reentry_cooldown_minutes,
                "trade_limit": 1,
                "only_per_pair": True,
                "only_per_side": True,
            },
        ]

    def _label_horizon(self) -> int:
        freqai_config = getattr(self, "freqai_info", {}) or {}
        feature_parameters = freqai_config.get("feature_parameters", {})
        return max(6, int(feature_parameters.get("label_period_candles", 24)))

    def feature_engineering_expand_all(
        self,
        dataframe: DataFrame,
        period: int,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe = super().feature_engineering_expand_all(dataframe, period, metadata, **kwargs)
        dataframe["%-atr-period"] = ta.ATR(dataframe, timeperiod=period)
        dataframe["%-atr_pct-period"] = dataframe["%-atr-period"] / dataframe["close"].replace(0, np.nan)
        dataframe["%-ema_spread-period"] = (
            ta.EMA(dataframe, timeperiod=max(2, period // 2)) - ta.EMA(dataframe, timeperiod=period)
        ) / dataframe["close"].replace(0, np.nan)
        dataframe["%-close_to_sma-period"] = dataframe["close"] / ta.SMA(dataframe, timeperiod=period)
        dataframe["%-hl_spread-period"] = (
            (dataframe["high"] - dataframe["low"]) / dataframe["close"].replace(0, np.nan)
        )
        return dataframe

    def feature_engineering_expand_basic(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe = super().feature_engineering_expand_basic(dataframe, metadata, **kwargs)
        dataframe["%-log_return"] = np.log(dataframe["close"] / dataframe["close"].shift(1))
        dataframe["%-candle_body"] = (
            (dataframe["close"] - dataframe["open"]) / dataframe["open"].replace(0, np.nan)
        )
        dataframe["%-wick_ratio"] = (
            (dataframe["high"] - dataframe[["open", "close"]].max(axis=1))
            + (dataframe[["open", "close"]].min(axis=1) - dataframe["low"])
        ) / dataframe["close"].replace(0, np.nan)
        return dataframe

    def feature_engineering_standard(
        self,
        dataframe: DataFrame,
        metadata: dict,
        **kwargs,
    ) -> DataFrame:
        dataframe = super().feature_engineering_standard(dataframe, metadata, **kwargs)
        ema_21 = ta.EMA(dataframe, timeperiod=21)
        ema_55 = ta.EMA(dataframe, timeperiod=55)
        ema_200 = ta.EMA(dataframe, timeperiod=200)
        dataframe["%-trend_bias"] = (ema_21 - ema_55) / dataframe["close"].replace(0, np.nan)
        dataframe["%-macro_bias"] = (dataframe["close"] - ema_200) / ema_200.replace(0, np.nan)
        dataframe["%-volume_zscore"] = (
            (dataframe["volume"] - dataframe["volume"].rolling(48).mean())
            / dataframe["volume"].rolling(48).std().replace(0, np.nan)
        )
        return dataframe

    def set_freqai_targets(self, dataframe: DataFrame, metadata: dict, **kwargs) -> DataFrame:
        self.freqai.class_names = ["down", "up"]
        horizon = self._label_horizon()
        future_return = dataframe["close"].shift(-horizon) / dataframe["close"] - 1.0
        rolling_volatility = dataframe["close"].pct_change().rolling(horizon).std()
        threshold = (rolling_volatility * 0.75).clip(lower=0.0025, upper=0.02)
        dataframe["&s-up_or_down"] = np.where(future_return > threshold, "up", "down")
        return dataframe

    def _probability_series(self, df: DataFrame, label: str) -> DataFrame:
        for candidate in (label, f"prob_{label}", f"{label}_prob"):
            if candidate in df.columns:
                return df[candidate].fillna(0.5)
        return df["do_predict"].fillna(0).astype(float) * 0 + 0.5

    def _resolve_component_probabilities(self, pair: str, row: dict) -> dict[str, float | int]:
        snapshot = _load_json(COMPONENT_SNAPSHOT_PATH)
        pair_records = snapshot.get("pairs", {})
        record = pair_records.get(pair, {}) if isinstance(pair_records, dict) else {}
        if not isinstance(record, dict):
            record = {}

        up_prob = _safe_float(row.get("up_prob"), 0.5)
        down_prob = _safe_float(row.get("down_prob"), 0.5)
        return {
            "ml_up_prob": _safe_float(record.get("ml_up_prob"), up_prob),
            "ml_down_prob": _safe_float(record.get("ml_down_prob"), down_prob),
            "dl_up_prob": _safe_float(record.get("dl_up_prob"), up_prob),
            "dl_down_prob": _safe_float(record.get("dl_down_prob"), down_prob),
            "ml_dl_agree": int(_safe_float(record.get("ml_dl_agree"), 0.0)),
        }

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe = self.freqai.start(dataframe, metadata, self)

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["mfi"] = ta.MFI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"].replace(0, np.nan)
        dataframe["ema_21"] = ta.EMA(dataframe, timeperiod=21)
        dataframe["ema_55"] = ta.EMA(dataframe, timeperiod=55)
        dataframe["ema_200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["tema"] = ta.TEMA(dataframe, timeperiod=9)
        macd = ta.MACD(dataframe)
        dataframe["macd"] = macd["macd"]
        dataframe["macdsignal"] = macd["macdsignal"]
        dataframe["macdhist"] = macd["macdhist"]
        dataframe["macdhist_prev"] = dataframe["macdhist"].shift(1)
        dataframe["rel_volume"] = dataframe["volume"] / dataframe["volume"].rolling(20).mean()
        dataframe["breakout_high"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["breakout_low"] = dataframe["low"].rolling(20).min().shift(1)
        dataframe["trend_strength"] = (dataframe["ema_21"] - dataframe["ema_55"]) / dataframe["close"].replace(
            0, np.nan
        )
        dataframe["up_prob"] = self._probability_series(dataframe, "up").astype(float)
        dataframe["down_prob"] = self._probability_series(dataframe, "down").astype(float)
        dataframe["ml_up_prob"] = dataframe["up_prob"].astype(float)
        dataframe["ml_down_prob"] = dataframe["down_prob"].astype(float)
        dataframe["dl_up_prob"] = dataframe["up_prob"].astype(float)
        dataframe["dl_down_prob"] = dataframe["down_prob"].astype(float)
        dataframe["ml_dl_agree"] = np.zeros(len(dataframe), dtype=np.int8)
        pair = metadata.get("pair")
        if pair and not dataframe.empty:
            component_probabilities = self._resolve_component_probabilities(
                pair,
                dataframe.iloc[-1].to_dict(),
            )
            last_index = dataframe.index[-1]
            for column, value in component_probabilities.items():
                dataframe.at[last_index, column] = value
        return dataframe

    def _high_confidence_gate(self, df: DataFrame, side: str) -> DataFrame:
        primary_label = "up" if side == "long" else "down"
        opposite_label = "down" if side == "long" else "up"
        return (
            (df[f"ml_{primary_label}_prob"] >= self.high_confidence_threshold)
            & (df[f"ml_{primary_label}_prob"] >= df[f"ml_{opposite_label}_prob"])
            & (df[f"dl_{primary_label}_prob"] >= self.high_confidence_threshold)
            & (df[f"dl_{primary_label}_prob"] >= df[f"dl_{opposite_label}_prob"])
        )

    def _strategy_blocked_reason(self, row: dict, side: str) -> str:
        is_long = side == "long"
        close = _safe_float(row.get("close"), 0.0)
        ema_21 = _safe_float(row.get("ema_21"), close)
        ema_55 = _safe_float(row.get("ema_55"), close)
        ema_200 = _safe_float(row.get("ema_200"), close)
        macdhist = _safe_float(row.get("macdhist"), 0.0)
        adx = _safe_float(row.get("adx"), 0.0)
        rel_volume = _safe_float(row.get("rel_volume"), 0.0)
        breakout_high = _safe_float(row.get("breakout_high"), close)
        breakout_low = _safe_float(row.get("breakout_low"), close)
        ml_primary = _safe_float(row.get("ml_up_prob" if is_long else "ml_down_prob"), 0.5)
        ml_opposite = _safe_float(row.get("ml_down_prob" if is_long else "ml_up_prob"), 0.5)
        dl_primary = _safe_float(row.get("dl_up_prob" if is_long else "dl_down_prob"), 0.5)
        dl_opposite = _safe_float(row.get("dl_down_prob" if is_long else "dl_up_prob"), 0.5)
        high_confidence = (
            ml_primary >= self.high_confidence_threshold
            and ml_primary >= ml_opposite
            and dl_primary >= self.high_confidence_threshold
            and dl_primary >= dl_opposite
        )
        rel_volume_min = (
            self.entry_high_conf_rel_volume_min if high_confidence else self.entry_rel_volume_min
        )
        fast_ema_tolerance = self.entry_fast_ema_tolerance_pct * (2.5 if high_confidence else 1.0)
        ema_stack_tolerance = self.entry_ema_stack_tolerance_pct * (3.0 if high_confidence else 1.0)
        ema200_tolerance = self.entry_ema200_tolerance_pct * (2.0 if high_confidence else 1.0)
        breakout_tolerance = self.entry_breakout_tolerance_pct * (2.0 if high_confidence else 1.0)
        macdhist_prev = _safe_float(row.get("macdhist_prev"), 0.0)

        blockers: list[str] = []
        if is_long:
            if close < ema_21 * (1 - fast_ema_tolerance):
                blockers.append("close below ema_21")
            if ema_21 < ema_55 * (1 - ema_stack_tolerance):
                blockers.append("ema_21 below ema_55")
            if close < ema_200 * (1 - ema200_tolerance):
                blockers.append("close below ema_200")
            if macdhist <= 0 and macdhist <= macdhist_prev:
                blockers.append("macdhist <= 0")
            if close < breakout_high * (1 - breakout_tolerance):
                blockers.append("breakout miss")
            if close / max(ema_21, 1e-9) > 1 + self.entry_max_ema_distance_pct:
                blockers.append("too far above ema_21")
        else:
            if close > ema_21 * (1 + fast_ema_tolerance):
                blockers.append("close above ema_21")
            if ema_21 > ema_55 * (1 + ema_stack_tolerance):
                blockers.append("ema_21 above ema_55")
            if close > ema_200 * (1 + ema200_tolerance):
                blockers.append("close above ema_200")
            if macdhist >= 0 and macdhist >= macdhist_prev:
                blockers.append("macdhist >= 0")
            if close > breakout_low * (1 + breakout_tolerance):
                blockers.append("breakout miss")
            if ema_21 / max(close, 1e-9) > 1 + self.entry_max_ema_distance_pct:
                blockers.append("too far below ema_21")

        if adx < self.entry_adx_min:
            blockers.append(f"adx {adx:.1f} < {self.entry_adx_min:.1f}")
        if rel_volume < rel_volume_min:
            blockers.append(f"rel_volume {rel_volume:.2f} < {rel_volume_min:.2f}")
        if _safe_float(row.get("volume"), 0.0) <= 0:
            blockers.append("volume <= 0")

        return ", ".join(blockers[:4]) if blockers else "trend/volume/breakout filters not met"

    def _build_side_stage_state(
        self,
        *,
        pair: str,
        side: str,
        row: dict,
        strategy_pass: bool,
        ml_pass: bool,
        dl_pass: bool,
    ) -> dict:
        is_long = side == "long"
        primary_label = "up" if is_long else "down"
        opposite_label = "down" if is_long else "up"
        ml_primary_prob = _safe_float(row.get(f"ml_{primary_label}_prob"), 0.5)
        ml_opposite_prob = _safe_float(row.get(f"ml_{opposite_label}_prob"), 0.5)
        dl_primary_prob = _safe_float(row.get(f"dl_{primary_label}_prob"), 0.5)
        dl_opposite_prob = _safe_float(row.get(f"dl_{opposite_label}_prob"), 0.5)
        ensemble_primary_prob = _safe_float(row.get(f"{primary_label}_prob"), 0.5)
        do_predict = int(_safe_float(row.get("do_predict"), 0.0))
        llm_signal = (llm_signal_for_pair(pair) or "HOLD").upper()
        llm_pass = not ((is_long and llm_signal == "SELL") or ((not is_long) and llm_signal == "BUY"))
        pipeline_pass = bool(strategy_pass and ml_pass and dl_pass and llm_pass)

        blocked_stage = None
        blocked_reason = None
        if not strategy_pass:
            blocked_stage = "strategy"
            blocked_reason = self._strategy_blocked_reason(row, side)
        elif not ml_pass:
            blocked_stage = "ml"
            if do_predict != 1:
                blocked_reason = f"FreqAI do_predict={do_predict}"
            else:
                blocked_reason = (
                    f"ML {primary_label} {ml_primary_prob * 100:.1f}% < {self.stage_probability_threshold * 100:.1f}% "
                    f"or opposite {ml_opposite_prob * 100:.1f}% stronger"
                )
        elif not dl_pass:
            blocked_stage = "dl"
            blocked_reason = (
                f"DL {primary_label} {dl_primary_prob * 100:.1f}% < {self.stage_probability_threshold * 100:.1f}% "
                f"or opposite {dl_opposite_prob * 100:.1f}% stronger"
            )
        elif not llm_pass:
            blocked_stage = "llm"
            blocked_reason = f"LLM veto {llm_signal}"

        return {
            "side": side,
            "strategy_pass": bool(strategy_pass),
            "ml_pass": bool(ml_pass),
            "dl_pass": bool(dl_pass),
            "llm_pass": bool(llm_pass),
            "pipeline_pass": pipeline_pass,
            "blocked_stage": blocked_stage,
            "blocked_reason": blocked_reason,
            "llm_signal": llm_signal,
            "ensemble_prob": round(ensemble_primary_prob, 4),
            "ml_prob": round(ml_primary_prob, 4),
            "ml_opposite_prob": round(ml_opposite_prob, 4),
            "dl_prob": round(dl_primary_prob, 4),
            "dl_opposite_prob": round(dl_opposite_prob, 4),
            "ml_dl_agree": bool(int(_safe_float(row.get("ml_dl_agree"), 0.0))),
            "enter_signal": bool(_safe_float(row.get("enter_long" if is_long else "enter_short"), 0.0) == 1.0),
            "enter_tag": row.get("enter_tag"),
        }

    def _update_pipeline_stage_snapshot(
        self,
        *,
        pair: str,
        row: dict,
        long_state: dict,
        short_state: dict,
    ) -> None:
        def _rank(stage_state: dict) -> tuple:
            return (
                int(stage_state["pipeline_pass"]),
                int(stage_state["llm_pass"]),
                int(stage_state["dl_pass"]),
                int(stage_state["ml_pass"]),
                int(stage_state["strategy_pass"]),
                stage_state["ensemble_prob"],
                stage_state["ml_prob"],
                stage_state["dl_prob"],
            )

        selected_state = max((long_state, short_state), key=_rank)
        payload = _load_json(PIPELINE_STAGE_SNAPSHOT_PATH)
        records = payload.get("pairs", {})
        records[pair] = {
            "pair": pair,
            "generated_at": _utc_now_z(),
            "close": round(_safe_float(row.get("close"), 0.0), 8),
            "selected_side": selected_state["side"] if selected_state["strategy_pass"] else "none",
            "selected_blocked_stage": selected_state["blocked_stage"],
            "selected_blocked_reason": selected_state["blocked_reason"],
            "long": long_state,
            "short": short_state,
            "selected": selected_state,
        }
        payload["generated_at"] = _utc_now_z()
        payload["pairs"] = records
        _write_json(PIPELINE_STAGE_SNAPSHOT_PATH, payload)

    def populate_entry_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        high_conf_long = self._high_confidence_gate(df, "long")
        high_conf_short = self._high_confidence_gate(df, "short")
        soft_adx_min = max(self.entry_adx_min - 2.0, 12.0)
        macd_turn_long = (df["macdhist"] > 0) | (high_conf_long & (df["macdhist"] > df["macdhist"].shift(1)))
        macd_turn_short = (df["macdhist"] < 0) | (high_conf_short & (df["macdhist"] < df["macdhist"].shift(1)))
        long_breakout_ready = (
            (df["close"] >= df["breakout_high"] * (1 - self.entry_breakout_tolerance_pct))
            | qtpylib.crossed_above(df["close"], df["ema_21"])
            | (high_conf_long & (df["close"] >= df["ema_21"] * (1 - self.entry_breakout_tolerance_pct * 2.0)))
        )
        short_breakout_ready = (
            (df["close"] <= df["breakout_low"] * (1 + self.entry_breakout_tolerance_pct))
            | qtpylib.crossed_below(df["close"], df["ema_21"])
            | (high_conf_short & (df["close"] <= df["ema_21"] * (1 + self.entry_breakout_tolerance_pct * 2.0)))
        )
        rel_volume_long = (df["rel_volume"] >= self.entry_rel_volume_min) | (
            high_conf_long & (df["rel_volume"] >= self.entry_high_conf_rel_volume_min)
        )
        rel_volume_short = (df["rel_volume"] >= self.entry_rel_volume_min) | (
            high_conf_short & (df["rel_volume"] >= self.entry_high_conf_rel_volume_min)
        )
        strategy_long = (
            (df["close"] >= df["ema_21"] * (1 - self.entry_fast_ema_tolerance_pct))
            & (
                (df["ema_21"] >= df["ema_55"] * (1 - self.entry_ema_stack_tolerance_pct))
                | (high_conf_long & (df["ema_21"] >= df["ema_55"] * (1 - self.entry_ema_stack_tolerance_pct * 3.0)))
            )
            & (
                (df["close"] >= df["ema_200"] * (1 - self.entry_ema200_tolerance_pct))
                | (high_conf_long & (df["close"] >= df["ema_200"] * (1 - self.entry_ema200_tolerance_pct * 2.0)))
            )
            & macd_turn_long
            & (df["adx"] >= self.entry_adx_min)
            & rel_volume_long
            & long_breakout_ready
            & ((df["close"] / df["ema_21"]) <= 1 + self.entry_max_ema_distance_pct)
            & (df["volume"] > 0)
        )
        retest_long = (
            high_conf_long
            & (df["close"] >= df["ema_21"] * (1 - self.entry_fast_ema_tolerance_pct * 4.0))
            & (df["ema_21"] >= df["ema_55"] * (1 - self.entry_ema_stack_tolerance_pct * 5.0))
            & (df["close"] >= df["ema_200"] * (1 - self.entry_ema200_tolerance_pct * 3.0))
            & (df["macdhist"] > df["macdhist"].shift(1))
            & (df["adx"] >= soft_adx_min)
            & (df["rel_volume"] >= self.entry_high_conf_rel_volume_min)
            & (df["volume"] > 0)
        )
        ml_long = (
            ((df["do_predict"] == 1) | high_conf_long)
            & (df["ml_up_prob"] >= self.stage_probability_threshold)
            & (df["ml_up_prob"] >= df["ml_down_prob"])
        )
        dl_long = (
            (df["dl_up_prob"] >= self.stage_probability_threshold)
            & (df["dl_up_prob"] >= df["dl_down_prob"])
        )
        strategy_long_effective = strategy_long | retest_long
        long_conditions = strategy_long & ml_long & dl_long
        df.loc[long_conditions, ["enter_long", "enter_tag"]] = (1, "aggressive_breakout_long")
        retest_long_conditions = (~long_conditions) & retest_long & ml_long & dl_long
        df.loc[retest_long_conditions, ["enter_long", "enter_tag"]] = (1, "aggressive_retest_long")

        strategy_short = (
            (df["close"] <= df["ema_21"] * (1 + self.entry_fast_ema_tolerance_pct))
            & (
                (df["ema_21"] <= df["ema_55"] * (1 + self.entry_ema_stack_tolerance_pct))
                | (high_conf_short & (df["ema_21"] <= df["ema_55"] * (1 + self.entry_ema_stack_tolerance_pct * 3.0)))
            )
            & (
                (df["close"] <= df["ema_200"] * (1 + self.entry_ema200_tolerance_pct))
                | (high_conf_short & (df["close"] <= df["ema_200"] * (1 + self.entry_ema200_tolerance_pct * 2.0)))
            )
            & macd_turn_short
            & (df["adx"] >= self.entry_adx_min)
            & rel_volume_short
            & short_breakout_ready
            & ((df["ema_21"] / df["close"]) <= 1 + self.entry_max_ema_distance_pct)
            & (df["volume"] > 0)
        )
        retest_short = (
            high_conf_short
            & (df["close"] <= df["ema_21"] * (1 + self.entry_fast_ema_tolerance_pct * 4.0))
            & (df["ema_21"] <= df["ema_55"] * (1 + self.entry_ema_stack_tolerance_pct * 5.0))
            & (df["close"] <= df["ema_200"] * (1 + self.entry_ema200_tolerance_pct * 3.0))
            & (df["macdhist"] < df["macdhist"].shift(1))
            & (df["adx"] >= soft_adx_min)
            & (df["rel_volume"] >= self.entry_high_conf_rel_volume_min)
            & (df["volume"] > 0)
        )
        ml_short = (
            ((df["do_predict"] == 1) | high_conf_short)
            & (df["ml_down_prob"] >= self.stage_probability_threshold)
            & (df["ml_down_prob"] >= df["ml_up_prob"])
        )
        dl_short = (
            (df["dl_down_prob"] >= self.stage_probability_threshold)
            & (df["dl_down_prob"] >= df["dl_up_prob"])
        )
        strategy_short_effective = strategy_short | retest_short
        short_conditions = strategy_short & ml_short & dl_short
        df.loc[short_conditions, ["enter_short", "enter_tag"]] = (1, "aggressive_breakout_short")
        retest_short_conditions = (~short_conditions) & retest_short & ml_short & dl_short
        df.loc[retest_short_conditions, ["enter_short", "enter_tag"]] = (1, "aggressive_retest_short")

        if not df.empty and metadata.get("pair"):
            row = df.iloc[-1].to_dict()
            long_state = self._build_side_stage_state(
                pair=metadata["pair"],
                side="long",
                row=row,
                strategy_pass=bool(strategy_long_effective.iloc[-1]),
                ml_pass=bool(ml_long.iloc[-1]),
                dl_pass=bool(dl_long.iloc[-1]),
            )
            short_state = self._build_side_stage_state(
                pair=metadata["pair"],
                side="short",
                row=row,
                strategy_pass=bool(strategy_short_effective.iloc[-1]),
                ml_pass=bool(ml_short.iloc[-1]),
                dl_pass=bool(dl_short.iloc[-1]),
            )
            self._update_pipeline_stage_snapshot(
                pair=metadata["pair"],
                row=row,
                long_state=long_state,
                short_state=short_state,
            )
        return df

    def populate_exit_trend(self, df: DataFrame, metadata: dict) -> DataFrame:
        df["exit_long"] = 0
        df["exit_short"] = 0
        return df

    def _last_candle(self, pair: str) -> dict | None:
        if not self.dp:
            return None
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return None
        return dataframe.iloc[-1].to_dict()

    def _trade_custom_float(self, trade: Trade, key: str, default: float = 0.0) -> float:
        return _safe_float(trade.get_custom_data(key, default), default)

    def _trade_custom_int(self, trade: Trade, key: str, default: int = 0) -> int:
        return int(round(self._trade_custom_float(trade, key, float(default))))

    def _trade_custom_bool(self, trade: Trade, key: str, default: bool = False) -> bool:
        value = trade.get_custom_data(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _recovery_target_from_peak(self, peak_profit: float) -> float:
        buffered_target = max(peak_profit - self.recovery_reclaim_buffer_pct, self.recovery_min_target_pct)
        ratio_target = peak_profit * self.recovery_reclaim_ratio
        return max(self.recovery_min_target_pct, min(peak_profit, max(buffered_target, ratio_target)))

    def _signal_alignment(self, pair: str, is_short: bool) -> dict[str, float | bool | str]:
        last_candle = self._last_candle(pair)
        side = "short" if is_short else "long"
        if not last_candle:
            return {
                "side": side,
                "aligned": False,
                "high_conf": False,
                "llm_ok": True,
                "primary_prob": 0.5,
                "ml_prob": 0.5,
                "dl_prob": 0.5,
                "opposite_prob": 0.5,
                "llm_signal": "HOLD",
            }

        primary_label = "down" if is_short else "up"
        opposite_label = "up" if is_short else "down"
        llm_signal = (llm_signal_for_pair(pair) or "HOLD").upper()
        llm_ok = not ((is_short and llm_signal == "BUY") or ((not is_short) and llm_signal == "SELL"))
        primary_prob = _safe_float(last_candle.get(f"{primary_label}_prob"), 0.5)
        opposite_prob = _safe_float(last_candle.get(f"{opposite_label}_prob"), 0.5)
        ml_prob = _safe_float(last_candle.get(f"ml_{primary_label}_prob"), primary_prob)
        dl_prob = _safe_float(last_candle.get(f"dl_{primary_label}_prob"), primary_prob)
        alignment_threshold = max(0.52, self.stage_probability_threshold - 0.04)
        high_conf_threshold = max(self.high_confidence_threshold, self.stage_probability_threshold + 0.08)
        aligned = (
            llm_ok
            and primary_prob >= alignment_threshold
            and ml_prob >= alignment_threshold
            and dl_prob >= alignment_threshold
            and primary_prob >= opposite_prob
        )
        high_conf = (
            aligned
            and primary_prob >= high_conf_threshold
            and ml_prob >= high_conf_threshold
            and dl_prob >= high_conf_threshold
        )
        return {
            "side": side,
            "aligned": aligned,
            "high_conf": high_conf,
            "llm_ok": llm_ok,
            "primary_prob": primary_prob,
            "ml_prob": ml_prob,
            "dl_prob": dl_prob,
            "opposite_prob": opposite_prob,
            "llm_signal": llm_signal,
        }

    def _sync_recovery_state(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_profit: float,
    ) -> dict[str, float | bool | int | str | None]:
        peak_profit = self._trade_custom_float(trade, "recovery_peak_profit", current_profit)
        if current_profit > peak_profit + 1e-6:
            peak_profit = current_profit
            trade.set_custom_data("recovery_peak_profit", round(peak_profit, 8))
            trade.set_custom_data("recovery_peak_profit_at", current_time.isoformat())
        elif trade.get_custom_data("recovery_peak_profit", None) is None:
            trade.set_custom_data("recovery_peak_profit", round(peak_profit, 8))
            trade.set_custom_data("recovery_peak_profit_at", current_time.isoformat())

        low_profit = self._trade_custom_float(trade, "recovery_low_profit", current_profit)
        if trade.get_custom_data("recovery_low_profit", None) is None or current_profit < low_profit:
            low_profit = current_profit
            trade.set_custom_data("recovery_low_profit", round(low_profit, 8))

        current_entries = max(int(getattr(trade, "nr_of_successful_entries", 1) or 1), 1)
        anchor_stake = self._trade_custom_float(trade, "recovery_anchor_stake", 0.0)
        if anchor_stake <= 0:
            anchor_stake = max(_safe_float(getattr(trade, "stake_amount", 0.0), 0.0) / current_entries, 0.0)
            if anchor_stake > 0:
                trade.set_custom_data("recovery_anchor_stake", round(anchor_stake, 8))

        recovery_armed = self._trade_custom_bool(trade, "recovery_mode_armed", False)
        recovery_target_profit = self._trade_custom_float(trade, "recovery_target_profit", 0.0)
        if (
            self.recovery_mode_enabled
            and peak_profit >= self.recovery_arm_peak_profit_pct
            and current_profit <= -self.recovery_activation_negative_pct
        ):
            recovery_target_profit = self._recovery_target_from_peak(peak_profit)
            if not recovery_armed:
                trade.set_custom_data("recovery_mode_armed", True)
                trade.set_custom_data("recovery_started_at", current_time.isoformat())
            trade.set_custom_data("recovery_target_profit", round(recovery_target_profit, 8))
            recovery_armed = True

        return {
            "armed": recovery_armed,
            "peak_profit": peak_profit,
            "low_profit": low_profit,
            "target_profit": recovery_target_profit,
            "anchor_stake": anchor_stake,
            "dca_level": self._trade_custom_int(trade, "recovery_last_dca_level", 0),
            "dca_count": max(current_entries - 1, 0),
            "last_dca_at": trade.get_custom_data("recovery_last_dca_at"),
        }

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time: datetime,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        last_candle = self._last_candle(pair)
        if not last_candle:
            return True

        llm_signal = llm_signal_for_pair(pair)
        if side == "long" and llm_signal == "SELL":
            return False
        if side == "short" and llm_signal == "BUY":
            return False

        close = float(last_candle.get("close") or rate)
        if side == "long" and rate > close * 1.0025:
            return False
        if side == "short" and rate < close * 0.9975:
            return False

        if side == "long" and float(last_candle.get("up_prob") or 0.5) < 0.55:
            return False
        if side == "short" and float(last_candle.get("down_prob") or 0.5) < 0.55:
            return False
        return True

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float | None:
        leverage = max(_safe_float(getattr(trade, "leverage", 1.0), 1.0), 1.0)
        trade_age_minutes = 0
        if trade.open_date_utc:
            trade_age_minutes = max(0, int((current_time - trade.open_date_utc).total_seconds() // 60))
        base_stoploss = -self.base_stoploss_pct
        if leverage >= 5.0:
            base_stoploss = max(base_stoploss, -0.023)
        elif leverage >= 4.0:
            base_stoploss = max(base_stoploss, -0.025)
        elif leverage >= 3.0:
            base_stoploss = max(base_stoploss, -0.028)

        recovery_state = self._sync_recovery_state(pair, trade, current_time, current_profit)
        if recovery_state["armed"] and current_profit < 0:
            recovery_floor = -(self.recovery_failsafe_pct + 0.004)
            base_stoploss = min(base_stoploss, recovery_floor)

        # Give high-conviction entries a little room to breathe before tightening.
        if trade_age_minutes < 10:
            return base_stoploss

        if current_profit >= 0.070:
            return -0.004
        if current_profit >= 0.055:
            return -0.007
        if current_profit >= 0.040:
            return -0.010
        if current_profit >= 0.028:
            return -0.013
        if current_profit >= 0.018:
            return -0.016
        if current_profit >= 0.010:
            return -0.020
        return base_stoploss

    def custom_roi(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        trade_duration: int,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float | None:
        if self._trade_custom_bool(trade, "recovery_mode_armed", False):
            recovery_target = self._trade_custom_float(trade, "recovery_target_profit", 0.0)
            if recovery_target > 0:
                return recovery_target
        if trade_duration < 20:
            return 0.050
        if trade_duration < 60:
            return 0.040
        if trade_duration < 180:
            return 0.030
        if trade_duration < 480:
            return 0.020
        if trade_duration < 720:
            return 0.012
        return 0.006

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> str | bool | None:
        if not trade.open_date_utc:
            return None

        trade_duration = int((current_time - trade.open_date_utc).total_seconds() // 60)
        last_candle = self._last_candle(pair)
        llm_signal = llm_signal_for_pair(pair)
        recovery_state = self._sync_recovery_state(pair, trade, current_time, current_profit)

        if recovery_state["armed"]:
            recovery_target = _safe_float(recovery_state["target_profit"], 0.0)
            if recovery_target > 0 and current_profit >= max(recovery_target - 0.0015, self.recovery_min_target_pct):
                return "recovery_reclaim_exit"
            if current_profit <= -self.recovery_failsafe_pct:
                return "recovery_fail_safe"
            if trade_duration >= self.recovery_max_hold_minutes and current_profit < 0:
                return "recovery_timeout_exit"
            alignment = self._signal_alignment(pair, trade.is_short)
            if not alignment["aligned"] and current_profit <= -0.014:
                return "recovery_thesis_break"
            return None

        if llm_signal == "SELL" and not trade.is_short and current_profit > 0.008:
            return "llm_veto_exit"
        if llm_signal == "BUY" and trade.is_short and current_profit > 0.008:
            return "llm_veto_exit"

        if trade_duration >= 480 and current_profit < -0.004:
            return "time_stop_deep"
        if trade_duration >= 240 and current_profit < -0.012:
            return "time_stop_loss"
        if trade_duration >= 120 and abs(current_profit) < 0.002:
            return "time_stop_flat"

        if last_candle:
            close = float(last_candle.get("close") or current_rate)
            ema_21 = float(last_candle.get("ema_21") or close)
            macdhist = float(last_candle.get("macdhist") or 0.0)
            rsi = float(last_candle.get("rsi") or 50.0)
            trend_strength = float(last_candle.get("trend_strength") or 0.0)
            adx = float(last_candle.get("adx") or 0.0)
            if not trade.is_short:
                if current_profit >= 0.018 and close < ema_21 and macdhist < 0:
                    return "profit_protect_long"
                if current_profit >= 0.025 and rsi >= 74 and macdhist < 0:
                    return "momentum_fade_long"
                if trade_duration >= 30 and current_profit < -0.012 and close < ema_21 and macdhist < 0 and rsi < 48:
                    return "trend_fail_long"
                if trade_duration >= 90 and current_profit < -0.006 and trend_strength <= 0 and adx < 16:
                    return "weak_edge_long"
                if trade_duration >= 180 and trend_strength < 0 and current_profit > 0.005:
                    return "trend_lost_long"
            else:
                if current_profit >= 0.018 and close > ema_21 and macdhist > 0:
                    return "profit_protect_short"
                if current_profit >= 0.025 and rsi <= 26 and macdhist > 0:
                    return "momentum_fade_short"
                if trade_duration >= 30 and current_profit < -0.012 and close > ema_21 and macdhist > 0 and rsi > 52:
                    return "trend_fail_short"
                if trade_duration >= 90 and current_profit < -0.006 and trend_strength >= 0 and adx < 16:
                    return "weak_edge_short"
                if trade_duration >= 180 and trend_strength > 0 and current_profit > 0.005:
                    return "trend_lost_short"

        return None

    def adjust_trade_position(
        self,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        min_stake: float | None,
        max_stake: float,
        current_entry_rate: float,
        current_exit_rate: float,
        current_entry_profit: float,
        current_exit_profit: float,
        **kwargs,
    ) -> float | None | tuple[float | None, str | None]:
        if not self.recovery_mode_enabled or trade.has_open_orders:
            return None
        if not trade.open_date_utc:
            return None

        trade_age_minutes = max(0, int((current_time - trade.open_date_utc).total_seconds() // 60))
        if trade_age_minutes < self.recovery_min_minutes_before_dca:
            return None

        recovery_state = self._sync_recovery_state(trade.pair, trade, current_time, current_profit)
        if not recovery_state["armed"] or current_profit >= 0:
            return None

        alignment = self._signal_alignment(trade.pair, trade.is_short)
        if not alignment["aligned"]:
            return None

        last_dca_level = int(recovery_state["dca_level"] or 0)
        last_dca_at_raw = recovery_state.get("last_dca_at")
        if isinstance(last_dca_at_raw, str):
            try:
                last_dca_at = datetime.fromisoformat(last_dca_at_raw.replace("Z", "+00:00"))
                if (current_time - last_dca_at).total_seconds() < self.recovery_dca_spacing_minutes * 60:
                    return None
            except ValueError:
                pass

        anchor_stake = _safe_float(recovery_state["anchor_stake"], 0.0)
        if anchor_stake <= 0:
            return None

        dca_levels = [
            {
                "level": 1,
                "loss_pct": self.dca_level1_loss_pct,
                "multiplier": self.dca_level1_multiplier,
                "require_high_conf": False,
            },
            {
                "level": 2,
                "loss_pct": self.dca_level2_loss_pct,
                "multiplier": self.dca_level2_multiplier,
                "require_high_conf": True,
            },
        ]

        for level in dca_levels:
            if level["level"] <= last_dca_level:
                continue
            if current_profit > -float(level["loss_pct"]):
                continue
            if level["require_high_conf"] and not alignment["high_conf"]:
                continue

            requested_stake = anchor_stake * float(level["multiplier"])
            if max_stake <= 0:
                return None
            stake_to_add = min(requested_stake, max_stake)
            if min_stake is not None and stake_to_add < min_stake:
                if max_stake < min_stake:
                    return None
                stake_to_add = min(max_stake, max(min_stake, requested_stake))
            if stake_to_add <= 0:
                return None

            order_tag = f"recovery_dca_{level['level']}"
            trade.set_custom_data("recovery_last_dca_level", int(level["level"]))
            trade.set_custom_data("recovery_last_dca_at", current_time.isoformat())
            trade.set_custom_data("recovery_last_adjustment_tag", order_tag)
            trade.set_custom_data("recovery_last_adjustment_profit", round(current_profit, 8))
            trade.set_custom_data(
                "recovery_dca_count",
                max(int(recovery_state["dca_count"] or 0), 0) + 1,
            )
            return stake_to_add, order_tag

        return None

    def leverage(
        self,
        pair: str,
        current_time: datetime,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        last_candle = self._last_candle(pair)
        default_leverage = max(1.0, _env_float("DEFAULT_LEVERAGE", 2.0))
        leverage_cap = max(1.0, min(self.max_live_leverage, max_leverage))
        leverage = min(max(float(proposed_leverage or 1.0), default_leverage), leverage_cap)

        if not last_candle:
            return max(1.0, leverage)

        probability_key = "up_prob" if side == "long" else "down_prob"
        confidence = float(last_candle.get(probability_key) or 0.5)
        adx = float(last_candle.get("adx") or 0.0)
        rel_volume = float(last_candle.get("rel_volume") or 1.0)
        atr_pct = float(last_candle.get("atr_pct") or 0.0)

        if leverage_cap >= 3.0 and confidence >= 0.66 and adx >= 20 and rel_volume >= 0.85 and atr_pct <= 0.055:
            leverage = max(leverage, min(3.0, leverage_cap))
        if leverage_cap >= 4.0 and confidence >= 0.80 and adx >= 24 and rel_volume >= 1.00 and 0.003 <= atr_pct <= 0.032:
            leverage = max(leverage, min(4.0, leverage_cap))
        if leverage_cap >= 5.0 and confidence >= 0.90 and adx >= 30 and rel_volume >= 1.30 and 0.004 <= atr_pct <= 0.028:
            leverage = max(leverage, min(5.0, leverage_cap))

        return max(1.0, min(leverage, leverage_cap, max_leverage))
