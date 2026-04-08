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

from logic.settings_env import load_settings_env
from trade.dynamic_stake_freqai_strategy import DynamicStakeFreqaiStrategy
from trade.llm_signal_bridge import llm_signal_for_pair

ROOT = Path(__file__).resolve().parents[1]
PIPELINE_STAGE_SNAPSHOT_PATH = ROOT / "runtime" / "pipeline_stage_snapshot.json"
COMPONENT_SNAPSHOT_PATH = ROOT / "runtime" / "freqai_component_snapshot.json"
SETTINGS_ENV_PATH = ROOT / "settings.env"
_SETTINGS_ENV_CACHE: dict[str, str] | None = None


def _env_float(name: str, default: float) -> float:
    global _SETTINGS_ENV_CACHE
    raw = os.getenv(name, "").strip()
    if not raw:
        if _SETTINGS_ENV_CACHE is None:
            try:
                _SETTINGS_ENV_CACHE = load_settings_env(SETTINGS_ENV_PATH)
            except Exception:
                _SETTINGS_ENV_CACHE = {}
        raw = (_SETTINGS_ENV_CACHE.get(name, "") if _SETTINGS_ENV_CACHE else "").strip()
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
    leverage_roi_profiles = (
        (5.0, ((20, 0.044), (60, 0.032), (180, 0.0230), (480, 0.0160), (720, 0.0110), (None, 0.0070))),
        (4.0, ((20, 0.038), (60, 0.028), (180, 0.0200), (480, 0.0140), (720, 0.0095), (None, 0.0060))),
        (3.0, ((20, 0.033), (60, 0.024), (180, 0.0170), (480, 0.0120), (720, 0.0080), (None, 0.0050))),
        (1.0, ((20, 0.028), (60, 0.020), (180, 0.0140), (480, 0.0100), (720, 0.0070), (None, 0.0040))),
    )
    leverage_profit_lock_profiles = (
        (5.0, ((0.013, -0.0150), (0.022, -0.0110), (0.032, -0.0080), (0.046, -0.0060), (0.062, -0.0040), (0.080, -0.0025))),
        (4.0, ((0.012, -0.0170), (0.020, -0.0125), (0.029, -0.0095), (0.041, -0.0070), (0.056, -0.0045), (0.072, -0.0030))),
        (3.0, ((0.011, -0.0190), (0.019, -0.0145), (0.028, -0.0110), (0.040, -0.0080), (0.053, -0.0055), (0.068, -0.0035))),
        (1.0, ((0.010, -0.0200), (0.018, -0.0160), (0.028, -0.0130), (0.040, -0.0100), (0.055, -0.0070), (0.070, -0.0040))),
    )
    stake_ratio = 0.10
    stage_probability_threshold = _env_float("AGGRESSIVE_STAGE_PROBABILITY_THRESHOLD", 0.54)
    long_stage_probability_threshold = _env_float(
        "AGGRESSIVE_LONG_STAGE_PROBABILITY_THRESHOLD",
        max(0.50, stage_probability_threshold - 0.03),
    )
    short_stage_probability_threshold = _env_float(
        "AGGRESSIVE_SHORT_STAGE_PROBABILITY_THRESHOLD",
        min(0.75, stage_probability_threshold + 0.03),
    )
    entry_adx_min = _env_float("AGGRESSIVE_ENTRY_ADX_MIN", 13.0)
    entry_long_adx_min = _env_float(
        "AGGRESSIVE_ENTRY_LONG_ADX_MIN",
        max(12.0, entry_adx_min - 2.0),
    )
    entry_short_adx_min = _env_float(
        "AGGRESSIVE_ENTRY_SHORT_ADX_MIN",
        entry_adx_min,
    )
    entry_rel_volume_min = _env_float("AGGRESSIVE_ENTRY_REL_VOLUME_MIN", 0.50)
    entry_high_conf_rel_volume_min = _env_float("AGGRESSIVE_HIGH_CONF_REL_VOLUME_MIN", 0.35)
    entry_long_rel_volume_min = _env_float(
        "AGGRESSIVE_ENTRY_LONG_REL_VOLUME_MIN",
        max(0.20, entry_rel_volume_min - 0.20),
    )
    entry_short_rel_volume_min = _env_float(
        "AGGRESSIVE_ENTRY_SHORT_REL_VOLUME_MIN",
        min(1.50, entry_rel_volume_min + 0.05),
    )
    entry_long_high_conf_rel_volume_min = _env_float(
        "AGGRESSIVE_ENTRY_LONG_HIGH_CONF_REL_VOLUME_MIN",
        max(0.15, entry_high_conf_rel_volume_min - 0.10),
    )
    entry_short_high_conf_rel_volume_min = _env_float(
        "AGGRESSIVE_ENTRY_SHORT_HIGH_CONF_REL_VOLUME_MIN",
        min(1.50, entry_high_conf_rel_volume_min + 0.05),
    )
    entry_breakout_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_BREAKOUT_TOLERANCE_PCT", 0.005)
    entry_long_breakout_tolerance_pct = _env_float(
        "AGGRESSIVE_ENTRY_LONG_BREAKOUT_TOLERANCE_PCT",
        entry_breakout_tolerance_pct * 2.0,
    )
    entry_short_breakout_tolerance_pct = _env_float(
        "AGGRESSIVE_ENTRY_SHORT_BREAKOUT_TOLERANCE_PCT",
        max(0.001, entry_breakout_tolerance_pct * 0.8),
    )
    entry_long_breakout_max_extension_pct = max(
        0.001,
        _env_float("AGGRESSIVE_ENTRY_LONG_BREAKOUT_MAX_EXTENSION_PCT", 0.010),
    )
    entry_short_breakout_max_extension_pct = max(
        0.001,
        _env_float("AGGRESSIVE_ENTRY_SHORT_BREAKOUT_MAX_EXTENSION_PCT", 0.006),
    )
    entry_retest_band_pct = max(
        0.001,
        _env_float("AGGRESSIVE_ENTRY_RETEST_BAND_PCT", 0.0035),
    )
    entry_breakout_recent_candles = max(
        2,
        int(_env_float("AGGRESSIVE_ENTRY_BREAKOUT_RECENT_CANDLES", 4)),
    )
    entry_fast_ema_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_FAST_EMA_TOLERANCE_PCT", 0.001)
    entry_ema_stack_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_EMA_STACK_TOLERANCE_PCT", 0.0005)
    entry_ema200_tolerance_pct = _env_float("AGGRESSIVE_ENTRY_EMA200_TOLERANCE_PCT", 0.002)
    entry_max_ema_distance_pct = _env_float("AGGRESSIVE_ENTRY_MAX_EMA_DISTANCE_PCT", 0.04)
    entry_trend_strength_min = max(0.0, _env_float("AGGRESSIVE_ENTRY_TREND_STRENGTH_MIN", 0.0015))
    entry_macro_bias_min = max(0.0, _env_float("AGGRESSIVE_ENTRY_MACRO_BIAS_MIN", 0.0025))
    entry_long_trend_strength_min = max(
        0.0,
        _env_float("AGGRESSIVE_ENTRY_LONG_TREND_STRENGTH_MIN", max(0.0005, entry_trend_strength_min * 0.5)),
    )
    entry_short_trend_strength_min = max(
        0.0,
        _env_float("AGGRESSIVE_ENTRY_SHORT_TREND_STRENGTH_MIN", entry_trend_strength_min * 1.2),
    )
    entry_long_macro_bias_min = max(
        0.0,
        _env_float("AGGRESSIVE_ENTRY_LONG_MACRO_BIAS_MIN", max(0.0008, entry_macro_bias_min * 0.5)),
    )
    entry_short_macro_bias_min = max(
        0.0,
        _env_float("AGGRESSIVE_ENTRY_SHORT_MACRO_BIAS_MIN", entry_macro_bias_min * 1.2),
    )
    entry_long_rsi_min = max(35.0, min(_env_float("AGGRESSIVE_ENTRY_LONG_RSI_MIN", 51.0), 80.0))
    entry_short_rsi_max = max(20.0, min(_env_float("AGGRESSIVE_ENTRY_SHORT_RSI_MAX", 49.0), 65.0))
    high_confidence_threshold = _env_float("AGGRESSIVE_HIGH_CONFIDENCE_THRESHOLD", 0.72)
    base_stoploss_pct = _env_float("AGGRESSIVE_BASE_STOPLOSS_PCT", 0.025)
    max_live_leverage = _env_float("AGGRESSIVE_MAX_LEVERAGE", 3.0)
    stoploss_guard_lookback_candles = max(
        6,
        int(_env_float("AGGRESSIVE_STOPLOSS_GUARD_LOOKBACK_CANDLES", 36)),
    )
    stoploss_guard_trade_limit = max(
        2,
        int(_env_float("AGGRESSIVE_STOPLOSS_GUARD_TRADE_LIMIT", 4)),
    )
    stoploss_guard_stop_candles = max(
        2,
        int(_env_float("AGGRESSIVE_STOPLOSS_GUARD_STOP_CANDLES", 20)),
    )
    max_drawdown_lookback_candles = max(
        12,
        int(_env_float("AGGRESSIVE_MAX_DRAWDOWN_LOOKBACK_CANDLES", 72)),
    )
    max_drawdown_trade_limit = max(
        4,
        int(_env_float("AGGRESSIVE_MAX_DRAWDOWN_TRADE_LIMIT", 12)),
    )
    max_drawdown_stop_candles = max(
        4,
        int(_env_float("AGGRESSIVE_MAX_DRAWDOWN_STOP_CANDLES", 20)),
    )
    max_allowed_drawdown = max(
        0.005,
        min(_env_float("AGGRESSIVE_MAX_ALLOWED_DRAWDOWN", 0.02), 0.20),
    )
    low_profit_short_lookback_candles = max(
        6,
        int(_env_float("AGGRESSIVE_LOW_PROFIT_LOOKBACK_CANDLES", 18)),
    )
    low_profit_short_trade_limit = max(
        2,
        int(_env_float("AGGRESSIVE_LOW_PROFIT_TRADE_LIMIT", 2)),
    )
    low_profit_short_stop_candles = max(
        4,
        int(_env_float("AGGRESSIVE_LOW_PROFIT_STOP_CANDLES", 30)),
    )
    low_profit_short_required_profit = _env_float("AGGRESSIVE_LOW_PROFIT_REQUIRED_PROFIT", 0.0)
    low_profit_long_lookback_candles = max(
        12,
        int(_env_float("AGGRESSIVE_LOW_PROFIT_LONG_LOOKBACK_CANDLES", 72)),
    )
    low_profit_long_trade_limit = max(
        2,
        int(_env_float("AGGRESSIVE_LOW_PROFIT_LONG_TRADE_LIMIT", 3)),
    )
    low_profit_long_stop_candles = max(
        4,
        int(_env_float("AGGRESSIVE_LOW_PROFIT_LONG_STOP_CANDLES", 60)),
    )
    low_profit_long_required_profit = _env_float("AGGRESSIVE_LOW_PROFIT_LONG_REQUIRED_PROFIT", 0.004)
    recovery_mode_enabled = _env_float("AGGRESSIVE_RECOVERY_MODE_ENABLED", 1.0) >= 0.5
    recovery_arm_peak_profit_pct = abs(_env_float("AGGRESSIVE_RECOVERY_ARM_PEAK_PCT", 1.2)) / 100.0
    recovery_activation_negative_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_NEGATIVE_ACTIVATION_PCT", 0.15)
    ) / 100.0
    recovery_preemptive_arm_minutes = max(
        1,
        int(_env_float("AGGRESSIVE_RECOVERY_PREEMPTIVE_ARM_MINUTES", 6)),
    )
    recovery_reclaim_ratio = max(
        0.55,
        min(_env_float("AGGRESSIVE_RECOVERY_RECLAIM_RATIO", 0.85), 0.99),
    )
    recovery_reclaim_buffer_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_RECLAIM_BUFFER_PCT", 0.40)
    ) / 100.0
    recovery_min_target_pct = abs(_env_float("AGGRESSIVE_RECOVERY_MIN_TARGET_PCT", 0.45)) / 100.0
    recovery_fee_per_side_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_FEE_PER_SIDE_PCT", 0.075)
    ) / 100.0
    recovery_fee_buffer_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_FEE_BUFFER_PCT", 0.03)
    ) / 100.0
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
    recovery_min_peak_before_dca_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_MIN_PEAK_BEFORE_DCA_PCT", 0.25)
    ) / 100.0
    recovery_level2_min_peak_before_dca_pct = abs(
        _env_float("AGGRESSIVE_RECOVERY_LEVEL2_MIN_PEAK_BEFORE_DCA_PCT", 0.60)
    ) / 100.0
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
        return "aggressive-v1.12"

    @property
    def protections(self) -> list[dict]:
        return [
            {
                "method": "CooldownPeriod",
                "stop_duration": self.pair_cooldown_minutes,
            },
            {
                "method": "StoplossGuard",
                "lookback_period_candles": self.stoploss_guard_lookback_candles,
                "trade_limit": self.stoploss_guard_trade_limit,
                "stop_duration_candles": self.stoploss_guard_stop_candles,
                "required_profit": 0.0,
                "only_per_pair": False,
                "only_per_side": True,
            },
            {
                "method": "MaxDrawdown",
                "calculation_mode": "equity",
                "lookback_period_candles": self.max_drawdown_lookback_candles,
                "trade_limit": self.max_drawdown_trade_limit,
                "stop_duration_candles": self.max_drawdown_stop_candles,
                "max_allowed_drawdown": self.max_allowed_drawdown,
            },
            {
                "method": "LowProfitPairs",
                "lookback_period_candles": self.low_profit_short_lookback_candles,
                "trade_limit": self.low_profit_short_trade_limit,
                "stop_duration_candles": self.low_profit_short_stop_candles,
                "required_profit": self.low_profit_short_required_profit,
                "only_per_side": True,
            },
            {
                "method": "LowProfitPairs",
                "lookback_period_candles": self.low_profit_long_lookback_candles,
                "trade_limit": self.low_profit_long_trade_limit,
                "stop_duration_candles": self.low_profit_long_stop_candles,
                "required_profit": self.low_profit_long_required_profit,
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
        dataframe["macro_bias"] = (dataframe["close"] - dataframe["ema_200"]) / dataframe["ema_200"].replace(
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
        trend_strength = _safe_float(row.get("trend_strength"), 0.0)
        macro_bias = _safe_float(row.get("macro_bias"), 0.0)
        rsi = _safe_float(row.get("rsi"), 50.0)
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
        if is_long:
            rel_volume_min = (
                self.entry_long_high_conf_rel_volume_min if high_confidence else self.entry_long_rel_volume_min
            )
            breakout_tolerance = self.entry_long_breakout_tolerance_pct * (2.5 if high_confidence else 1.0)
        else:
            rel_volume_min = (
                self.entry_short_high_conf_rel_volume_min if high_confidence else self.entry_short_rel_volume_min
            )
            breakout_tolerance = self.entry_short_breakout_tolerance_pct * (1.5 if high_confidence else 1.0)
        fast_ema_tolerance = self.entry_fast_ema_tolerance_pct * (2.5 if high_confidence else 1.0)
        ema_stack_tolerance = self.entry_ema_stack_tolerance_pct * (3.0 if high_confidence else 1.0)
        ema200_tolerance = self.entry_ema200_tolerance_pct * (2.0 if high_confidence else 1.0)
        macdhist_prev = _safe_float(row.get("macdhist_prev"), 0.0)

        blockers: list[str] = []
        if is_long:
            trend_threshold = self.entry_long_trend_strength_min * (0.45 if high_confidence else 1.0)
            macro_threshold = self.entry_long_macro_bias_min * (0.45 if high_confidence else 1.0)
            rsi_threshold = self.entry_long_rsi_min - (4.0 if high_confidence else 0.0)
            if close < ema_21 * (1 - fast_ema_tolerance):
                blockers.append("close below ema_21")
            if ema_21 < ema_55 * (1 - ema_stack_tolerance):
                blockers.append("ema_21 below ema_55")
            if close < ema_200 * (1 - ema200_tolerance):
                blockers.append("close below ema_200")
            if trend_strength < trend_threshold:
                blockers.append(f"trend_strength {trend_strength:.4f} < {trend_threshold:.4f}")
            if macro_bias < macro_threshold:
                blockers.append(f"macro_bias {macro_bias:.4f} < {macro_threshold:.4f}")
            if rsi < rsi_threshold:
                blockers.append(f"rsi {rsi:.1f} < {rsi_threshold:.1f}")
            if macdhist <= 0 and macdhist <= macdhist_prev:
                blockers.append("macdhist <= 0")
            if close < breakout_high * (1 - breakout_tolerance):
                blockers.append("breakout miss")
            if close > breakout_high * (1 + self.entry_long_breakout_max_extension_pct):
                blockers.append("too far above breakout")
            if close / max(ema_21, 1e-9) > 1 + self.entry_max_ema_distance_pct:
                blockers.append("too far above ema_21")
        else:
            trend_threshold = -self.entry_short_trend_strength_min * (0.65 if high_confidence else 1.0)
            macro_threshold = -self.entry_short_macro_bias_min * (0.65 if high_confidence else 1.0)
            rsi_threshold = self.entry_short_rsi_max + (3.0 if high_confidence else 0.0)
            if close > ema_21 * (1 + fast_ema_tolerance):
                blockers.append("close above ema_21")
            if ema_21 > ema_55 * (1 + ema_stack_tolerance):
                blockers.append("ema_21 above ema_55")
            if close > ema_200 * (1 + ema200_tolerance):
                blockers.append("close above ema_200")
            if trend_strength > trend_threshold:
                blockers.append(f"trend_strength {trend_strength:.4f} > {trend_threshold:.4f}")
            if macro_bias > macro_threshold:
                blockers.append(f"macro_bias {macro_bias:.4f} > {macro_threshold:.4f}")
            if rsi > rsi_threshold:
                blockers.append(f"rsi {rsi:.1f} > {rsi_threshold:.1f}")
            if macdhist >= 0 and macdhist >= macdhist_prev:
                blockers.append("macdhist >= 0")
            if close > breakout_low * (1 + breakout_tolerance):
                blockers.append("breakout miss")
            if close < breakout_low * (1 - self.entry_short_breakout_max_extension_pct):
                blockers.append("too far below breakout")
            if ema_21 / max(close, 1e-9) > 1 + self.entry_max_ema_distance_pct:
                blockers.append("too far below ema_21")

        adx_threshold = self.entry_long_adx_min if is_long else self.entry_short_adx_min
        if adx < adx_threshold:
            blockers.append(f"adx {adx:.1f} < {adx_threshold:.1f}")
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
        side_probability_threshold = (
            self.long_stage_probability_threshold if is_long else self.short_stage_probability_threshold
        )
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
                    f"ML {primary_label} {ml_primary_prob * 100:.1f}% < {side_probability_threshold * 100:.1f}% "
                    f"or opposite {ml_opposite_prob * 100:.1f}% stronger"
                )
        elif not dl_pass:
            blocked_stage = "dl"
            blocked_reason = (
                f"DL {primary_label} {dl_primary_prob * 100:.1f}% < {side_probability_threshold * 100:.1f}% "
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
        long_adx_min = min(self.entry_adx_min, self.entry_long_adx_min)
        short_adx_min = max(self.entry_short_adx_min, self.entry_adx_min)
        long_probability_threshold = self.long_stage_probability_threshold
        short_probability_threshold = self.short_stage_probability_threshold
        bullish_breakout_candle = df["close"] >= df["open"]
        bearish_breakdown_candle = df["close"] <= df["open"]
        macd_turn_long = (df["macdhist"] > 0) | (high_conf_long & (df["macdhist"] > df["macdhist"].shift(1)))
        macd_turn_short = (df["macdhist"] < 0) | (high_conf_short & (df["macdhist"] < df["macdhist"].shift(1)))
        long_breakout_fresh = (
            qtpylib.crossed_above(df["close"], df["breakout_high"])
            | (
                (df["close"] >= df["breakout_high"] * (1 - self.entry_long_breakout_tolerance_pct))
                & (df["close"].shift(1) < df["breakout_high"].shift(1) * (1 - self.entry_long_breakout_tolerance_pct * 0.5))
            )
        )
        short_breakout_fresh = (
            qtpylib.crossed_below(df["close"], df["breakout_low"])
            | (
                (df["close"] <= df["breakout_low"] * (1 + self.entry_short_breakout_tolerance_pct))
                & (df["close"].shift(1) > df["breakout_low"].shift(1) * (1 + self.entry_short_breakout_tolerance_pct * 0.5))
            )
        )
        long_breakout_ready = (
            long_breakout_fresh
            & (df["close"] <= df["breakout_high"] * (1 + self.entry_long_breakout_max_extension_pct))
            & bullish_breakout_candle
        )
        short_breakout_ready = (
            short_breakout_fresh
            & (df["close"] >= df["breakout_low"] * (1 - self.entry_short_breakout_max_extension_pct))
            & bearish_breakdown_candle
        )
        recent_long_breakout = (
            df["close"].shift(1).rolling(self.entry_breakout_recent_candles).max()
            >= df["breakout_high"] * (1 - self.entry_long_breakout_tolerance_pct)
        )
        recent_short_breakdown = (
            df["close"].shift(1).rolling(self.entry_breakout_recent_candles).min()
            <= df["breakout_low"] * (1 + self.entry_short_breakout_tolerance_pct)
        )
        long_retest_band = (
            (df["close"] >= df["breakout_high"] * (1 - self.entry_retest_band_pct))
            & (df["close"] <= df["breakout_high"] * (1 + self.entry_retest_band_pct * 2.0))
        )
        short_retest_band = (
            (df["close"] <= df["breakout_low"] * (1 + self.entry_retest_band_pct))
            & (df["close"] >= df["breakout_low"] * (1 - self.entry_retest_band_pct * 2.0))
        )
        rel_volume_long = (df["rel_volume"] >= self.entry_long_rel_volume_min) | (
            high_conf_long & (df["rel_volume"] >= self.entry_long_high_conf_rel_volume_min)
        )
        rel_volume_short = (df["rel_volume"] >= self.entry_short_rel_volume_min) | (
            high_conf_short & (df["rel_volume"] >= self.entry_short_high_conf_rel_volume_min)
        )
        trend_bias_long = (df["trend_strength"] >= self.entry_long_trend_strength_min) | (
            high_conf_long & (df["trend_strength"] >= self.entry_long_trend_strength_min * 0.45)
        )
        trend_bias_short = (df["trend_strength"] <= -self.entry_short_trend_strength_min) | (
            high_conf_short & (df["trend_strength"] <= -(self.entry_short_trend_strength_min * 0.65))
        )
        macro_bias_long = (df["macro_bias"] >= self.entry_long_macro_bias_min) | (
            high_conf_long & (df["macro_bias"] >= self.entry_long_macro_bias_min * 0.45)
        )
        macro_bias_short = (df["macro_bias"] <= -self.entry_short_macro_bias_min) | (
            high_conf_short & (df["macro_bias"] <= -(self.entry_short_macro_bias_min * 0.65))
        )
        rsi_gate_long = (df["rsi"] >= self.entry_long_rsi_min) | (
            high_conf_long & (df["rsi"] >= self.entry_long_rsi_min - 4.0)
        )
        rsi_gate_short = (df["rsi"] <= self.entry_short_rsi_max) | (
            high_conf_short & (df["rsi"] <= self.entry_short_rsi_max + 4.0)
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
            & trend_bias_long
            & macro_bias_long
            & rsi_gate_long
            & macd_turn_long
            & (df["adx"] >= long_adx_min)
            & rel_volume_long
            & long_breakout_ready
            & ((df["close"] / df["ema_21"]) <= 1 + self.entry_max_ema_distance_pct)
            & (df["volume"] > 0)
        )
        retest_long = (
            high_conf_long
            & recent_long_breakout
            & long_retest_band
            & (df["close"] >= df["ema_21"] * (1 - self.entry_fast_ema_tolerance_pct * 4.0))
            & (df["ema_21"] >= df["ema_55"] * (1 - self.entry_ema_stack_tolerance_pct * 5.0))
            & (df["close"] >= df["ema_200"] * (1 - self.entry_ema200_tolerance_pct * 3.0))
            & trend_bias_long
            & macro_bias_long
            & (df["rsi"] >= self.entry_long_rsi_min - 5.0)
            & (df["macdhist"] > df["macdhist"].shift(1))
            & (df["adx"] >= soft_adx_min)
            & (df["rel_volume"] >= self.entry_long_high_conf_rel_volume_min)
            & (df["volume"] > 0)
        )
        reversal_long = (
            high_conf_long
            & (df["close"] >= df["ema_21"] * (1 - self.entry_long_breakout_tolerance_pct * 2.5))
            & (df["close"] >= df["ema_55"] * (1 - self.entry_long_breakout_tolerance_pct * 2.0))
            & (df["close"] >= df["ema_200"] * (1 - self.entry_ema200_tolerance_pct * 3.0))
            & (df["trend_strength"] >= -(self.entry_long_trend_strength_min * 0.5))
            & (df["macro_bias"] >= -(self.entry_long_macro_bias_min * 0.5))
            & (df["rsi"] >= max(self.entry_long_rsi_min - 6.0, 40.0))
            & (df["macdhist"] > df["macdhist"].shift(1))
            & (df["adx"] >= max(12.0, long_adx_min - 1.0))
            & (df["rel_volume"] >= self.entry_long_high_conf_rel_volume_min)
            & (df["volume"] > 0)
        )
        ml_long = (
            ((df["do_predict"] == 1) | high_conf_long)
            & (df["ml_up_prob"] >= long_probability_threshold)
            & (df["ml_up_prob"] >= df["ml_down_prob"])
        )
        dl_long = (
            (df["dl_up_prob"] >= long_probability_threshold)
            & (df["dl_up_prob"] >= df["dl_down_prob"])
        )
        strategy_long_effective = strategy_long | retest_long | reversal_long
        long_conditions = strategy_long & ml_long & dl_long
        df.loc[long_conditions, ["enter_long", "enter_tag"]] = (1, "aggressive_breakout_long")
        retest_long_conditions = (~long_conditions) & retest_long & ml_long & dl_long
        df.loc[retest_long_conditions, ["enter_long", "enter_tag"]] = (1, "aggressive_retest_long")
        reversal_long_conditions = (~long_conditions) & (~retest_long_conditions) & reversal_long & ml_long & dl_long
        df.loc[reversal_long_conditions, ["enter_long", "enter_tag"]] = (1, "aggressive_reversal_long")

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
            & trend_bias_short
            & macro_bias_short
            & rsi_gate_short
            & macd_turn_short
            & (df["adx"] >= short_adx_min)
            & rel_volume_short
            & short_breakout_ready
            & ((df["ema_21"] / df["close"]) <= 1 + self.entry_max_ema_distance_pct)
            & (df["volume"] > 0)
        )
        retest_short = (
            high_conf_short
            & recent_short_breakdown
            & short_retest_band
            & (df["close"] <= df["ema_21"] * (1 + self.entry_fast_ema_tolerance_pct * 4.0))
            & (df["ema_21"] <= df["ema_55"] * (1 + self.entry_ema_stack_tolerance_pct * 5.0))
            & (df["close"] <= df["ema_200"] * (1 + self.entry_ema200_tolerance_pct * 3.0))
            & trend_bias_short
            & macro_bias_short
            & (df["rsi"] <= self.entry_short_rsi_max + 5.0)
            & (df["macdhist"] < df["macdhist"].shift(1))
            & (df["adx"] >= soft_adx_min)
            & (df["rel_volume"] >= self.entry_short_high_conf_rel_volume_min)
            & (df["volume"] > 0)
        )
        ml_short = (
            ((df["do_predict"] == 1) | high_conf_short)
            & (df["ml_down_prob"] >= short_probability_threshold)
            & (df["ml_down_prob"] >= df["ml_up_prob"])
        )
        dl_short = (
            (df["dl_down_prob"] >= short_probability_threshold)
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

    def _recovery_min_target_for_trade(self, trade: Trade) -> float:
        leverage_value = max(_safe_float(getattr(trade, "leverage", 1.0), 1.0), 1.0)
        fee_open_rate = max(
            self.recovery_fee_per_side_pct,
            _safe_float(getattr(trade, "fee_open", 0.0), 0.0),
        )
        fee_close_rate = max(
            self.recovery_fee_per_side_pct,
            _safe_float(getattr(trade, "fee_close", fee_open_rate), fee_open_rate),
        )
        round_trip_fee_pct = (fee_open_rate + fee_close_rate) * leverage_value
        return max(self.recovery_min_target_pct, round_trip_fee_pct + self.recovery_fee_buffer_pct)

    def _recovery_target_from_peak(self, peak_profit: float, min_target_profit: float) -> float:
        buffered_target = max(peak_profit - self.recovery_reclaim_buffer_pct, min_target_profit)
        ratio_target = peak_profit * self.recovery_reclaim_ratio
        return max(min_target_profit, min(peak_profit, max(buffered_target, ratio_target)))

    @classmethod
    def _roi_schedule_for_leverage(cls, leverage: float) -> tuple[tuple[int | None, float], ...]:
        leverage = max(_safe_float(leverage, 1.0), 1.0)
        for min_leverage, schedule in cls.leverage_roi_profiles:
            if leverage >= min_leverage:
                return schedule
        return cls.leverage_roi_profiles[-1][1]

    @classmethod
    def _profit_lock_schedule_for_leverage(cls, leverage: float) -> tuple[tuple[float, float], ...]:
        leverage = max(_safe_float(leverage, 1.0), 1.0)
        for min_leverage, schedule in cls.leverage_profit_lock_profiles:
            if leverage >= min_leverage:
                return schedule
        return cls.leverage_profit_lock_profiles[-1][1]

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
        trade_age_minutes = 0
        if trade.open_date_utc:
            trade_age_minutes = max(0, int((current_time - trade.open_date_utc).total_seconds() // 60))
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
        min_target_profit = self._recovery_min_target_for_trade(trade)
        alignment = self._signal_alignment(pair, trade.is_short)
        standard_recovery_trigger = (
            peak_profit >= self.recovery_arm_peak_profit_pct
            and current_profit <= -self.recovery_activation_negative_pct
        )
        preemptive_recovery_trigger = (
            trade_age_minutes >= self.recovery_preemptive_arm_minutes
            and current_profit <= -self.recovery_activation_negative_pct
            and alignment["aligned"]
        )
        if recovery_armed:
            target_anchor = max(peak_profit, min_target_profit)
            recovery_target_profit = self._recovery_target_from_peak(target_anchor, min_target_profit)
            trade.set_custom_data("recovery_target_profit", round(recovery_target_profit, 8))
        elif self.recovery_mode_enabled and (standard_recovery_trigger or preemptive_recovery_trigger):
            target_anchor = max(peak_profit, min_target_profit)
            recovery_target_profit = self._recovery_target_from_peak(target_anchor, min_target_profit)
            if not recovery_armed:
                trade.set_custom_data("recovery_mode_armed", True)
                trade.set_custom_data("recovery_started_at", current_time.isoformat())
                trade.set_custom_data(
                    "recovery_activation_reason",
                    "peak_reclaim" if standard_recovery_trigger else "preemptive_negative_recovery",
                )
            trade.set_custom_data("recovery_target_profit", round(recovery_target_profit, 8))
            recovery_armed = True

        return {
            "armed": recovery_armed,
            "peak_profit": peak_profit,
            "low_profit": low_profit,
            "target_profit": recovery_target_profit,
            "min_target_profit": min_target_profit,
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

        for min_profit, lock_stoploss in self._profit_lock_schedule_for_leverage(leverage):
            if current_profit >= min_profit:
                return lock_stoploss
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
        leverage = max(_safe_float(getattr(trade, "leverage", 1.0), 1.0), 1.0)
        if self._trade_custom_bool(trade, "recovery_mode_armed", False):
            recovery_target = self._trade_custom_float(trade, "recovery_target_profit", 0.0)
            recovery_min_target = self._recovery_min_target_for_trade(trade)
            if recovery_target > 0:
                return max(recovery_target, recovery_min_target)
        for max_duration, target_pct in self._roi_schedule_for_leverage(leverage):
            if max_duration is None or trade_duration < max_duration:
                return target_pct
        return self._roi_schedule_for_leverage(leverage)[-1][1]

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
        peak_profit = _safe_float(recovery_state.get("peak_profit"), current_profit)

        if recovery_state["armed"]:
            recovery_target = _safe_float(recovery_state["target_profit"], 0.0)
            recovery_min_target = _safe_float(
                recovery_state.get("min_target_profit"),
                self.recovery_min_target_pct,
            )
            if recovery_target > 0 and current_profit >= max(recovery_target - 0.0015, recovery_min_target):
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
                if current_profit >= 0.010 and close < ema_21 and macdhist < 0:
                    return "profit_protect_long"
                if current_profit >= 0.018 and rsi >= 72 and macdhist < 0:
                    return "momentum_fade_long"
                if trade_duration >= 24 and peak_profit < 0.003 and current_profit < -0.010 and close < ema_21:
                    return "dead_trade_long"
                if trade_duration >= 32 and current_profit < -0.012 and close < ema_21 and macdhist < 0 and rsi < 49:
                    return "trend_fail_long"
                if trade_duration >= 60 and current_profit < -0.004 and trend_strength <= 0 and adx < 18:
                    return "weak_edge_long"
                if trade_duration >= 180 and trend_strength < 0 and current_profit > 0.005:
                    return "trend_lost_long"
            else:
                if current_profit >= 0.010 and close > ema_21 and macdhist > 0:
                    return "profit_protect_short"
                if current_profit >= 0.018 and rsi <= 28 and macdhist > 0:
                    return "momentum_fade_short"
                if trade_duration >= 24 and peak_profit < 0.003 and current_profit < -0.010 and close > ema_21:
                    return "dead_trade_short"
                if trade_duration >= 32 and current_profit < -0.012 and close > ema_21 and macdhist > 0 and rsi > 51:
                    return "trend_fail_short"
                if trade_duration >= 60 and current_profit < -0.004 and trend_strength >= 0 and adx < 18:
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
        peak_profit = _safe_float(recovery_state["peak_profit"], current_profit)

        dca_levels = [
            {
                "level": 1,
                "loss_pct": self.dca_level1_loss_pct,
                "multiplier": self.dca_level1_multiplier,
                "require_high_conf": False,
                "min_peak_profit": self.recovery_min_peak_before_dca_pct,
            },
            {
                "level": 2,
                "loss_pct": self.dca_level2_loss_pct,
                "multiplier": self.dca_level2_multiplier,
                "require_high_conf": True,
                "min_peak_profit": self.recovery_level2_min_peak_before_dca_pct,
            },
        ]

        for level in dca_levels:
            if level["level"] <= last_dca_level:
                continue
            if current_profit > -float(level["loss_pct"]):
                continue
            if level["require_high_conf"] and not alignment["high_conf"]:
                continue
            if peak_profit < float(level["min_peak_profit"]) and not alignment["high_conf"]:
                continue
            if level["level"] >= 2 and peak_profit < float(level["min_peak_profit"]):
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
