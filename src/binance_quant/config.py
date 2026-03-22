from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

import yaml


T = TypeVar("T")


@dataclass
class PathConfig:
    data_root: str = "data"
    cache_root: str = "data/cache"
    market_data_root: str = "data/market"
    artifact_root: str = "artifacts"
    registry_db: str = "artifacts/registry/experiments.sqlite3"


@dataclass
class ExchangeConfig:
    base_rest_url: str = "https://fapi.binance.com"
    base_ws_url: str = "wss://fstream.binance.com"
    exchange_info_ttl_minutes: int = 360
    universe_ttl_minutes: int = 30
    ticker_ttl_minutes: int = 10
    request_timeout_seconds: int = 20
    max_retry_attempts: int = 5
    base_retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 30.0
    request_weight_cap_per_minute: int = 2000
    request_weight_budgets: dict[str, int] = field(
        default_factory=lambda: {
            "metadata": 200,
            "market_data": 1600,
            "account": 100,
            "orders": 100,
        }
    )
    kline_request_limit: int = 1000
    websocket_message_cap_per_second: int = 10
    websocket_rotate_hours: int = 24
    websocket_ping_interval_seconds: int = 30
    websocket_ping_timeout_seconds: int = 60
    websocket_open_timeout_seconds: int = 30
    websocket_close_timeout_seconds: int = 10
    websocket_reconnect_delay_seconds: float = 5.0


@dataclass
class UniverseConfig:
    allowed_quote_assets: list[str] = field(default_factory=lambda: ["USDT", "USDC"])
    allowed_contract_types: list[str] = field(
        default_factory=lambda: ["PERPETUAL", "CURRENT_QUARTER", "NEXT_QUARTER"]
    )
    min_24h_quote_volume_usd: float = 10_000_000
    min_history_days: int = 90
    min_last_price: float = 0.0
    max_symbols: int = 8
    unique_base_assets_only: bool = True
    exclude_symbols: list[str] = field(default_factory=list)
    include_symbols: list[str] = field(default_factory=list)


@dataclass
class DataConfig:
    timeframe: str = "15m"
    backfill_days: int = 120
    chunk_days: int = 14
    parquet_compression: str = "zstd"
    require_full_alignment: bool = True


@dataclass
class BacktestConfig:
    leverage: float = 10.0
    capital_fraction_per_trade: float = 0.1
    fee_bps_per_side: float = 4.0
    slippage_bps_per_side: float = 1.5
    stop_atr_multiple: float = 1.5
    target_atr_multiple: float = 2.5
    max_holding_bars: int = 48
    max_concurrent_positions: int = 3
    liquidation_buffer_fraction: float = 0.9
    liquidation_loss_fraction: float = 0.98
    min_trade_count: int = 40


@dataclass
class LabelingConfig:
    horizon_bars: int = 48
    target_atr_multiple: float = 2.5
    stop_atr_multiple: float = 1.5
    max_adverse_excursion_limit: float = 0.03


@dataclass
class ResearchConfig:
    random_seed: int = 42
    min_candidate_trades: int = 50
    min_profit_factor: float = 1.03
    min_expectancy: float = 0.0005
    max_drawdown_fraction: float = 0.4
    relaxed_min_profit_factor: float = 0.92
    relaxed_min_expectancy: float = -0.0008
    relaxed_max_drawdown_fraction: float = 0.45
    relaxed_min_positive_symbols: int = 2
    family_seed_profit_factor_margin: float = 0.03
    family_seed_expectancy_margin: float = 0.0005
    family_seed_max_drawdown_buffer: float = 0.05
    max_survivors_per_family: int = 2
    max_signal_overlap: float = 0.6
    min_survivor_count: int = 3
    monte_carlo_iterations: int = 250
    feature_correlation_threshold: float = 0.95


@dataclass
class MLConfig:
    enabled: bool = True
    min_events: int = 200
    folds: int = 3
    train_fraction: float = 0.55
    validation_fraction: float = 0.2
    test_fraction: float = 0.15
    calibration_fraction_of_validation: float = 0.5
    embargo_bars: int = 4
    min_acceptance_rate: float = 0.1
    max_acceptance_rate: float = 0.7
    threshold_grid: list[float] = field(
        default_factory=lambda: [0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]
    )
    cost_stress_bps_per_side: float = 2.0
    calibration_methods: list[str] = field(default_factory=lambda: ["platt", "isotonic"])
    models: list[str] = field(
        default_factory=lambda: ["logistic_regression", "random_forest", "xgboost"]
    )


@dataclass
class PortfolioConfig:
    max_trades_per_day: int = 20
    max_concurrent_positions: int = 4
    max_symbol_weight: float = 0.35
    max_strategy_weight: float = 0.5
    min_portfolio_trades: int = 10
    min_distinct_symbols: int = 3
    min_distinct_families: int = 2
    daily_loss_limit_fraction: float = 0.08
    volatility_kill_switch_quantile: float = 0.98


@dataclass
class ReportingConfig:
    save_json: bool = True
    save_markdown: bool = True
    save_csv: bool = True


@dataclass
class DeploymentConfig:
    bundle_path: str = "artifacts/deployment/paper_bundle.pkl"
    manifest_path: str = "artifacts/deployment/paper_manifest.json"
    source_artifact: str = "latest_accepted"
    auto_rebuild_on_start: bool = True
    calibration_fraction: float = 0.2
    minimum_calibration_events: int = 80


@dataclass
class PaperConfig:
    state_db: str = "artifacts/paper/paper_state.sqlite3"
    log_path: str = "artifacts/latest/paper_runtime.log"
    initial_lookback_bars: int = 600
    max_runtime_bars: int = 1200
    position_check_interval_seconds: int = 2
    enable_signal_exit: bool = True
    allow_one_position_per_symbol: bool = True
    auto_retune: bool = True
    retune_interval_hours: int = 24
    retune_check_seconds: int = 300
    initial_retune_delay_seconds: int = 90
    summary_window_days: int = 7
    auto_rebuild_deployment: bool = True


@dataclass
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    reload: bool = False
    decision_log_limit: int = 100
    closed_trade_limit: int = 100
    log_tail_lines: int = 200


@dataclass
class LocalLLMConfig:
    enabled: bool = True
    provider: str = "ollama"
    base_url: str = "http://127.0.0.1:11434"
    model: str = "qwen3:14b"
    timeout_seconds: int = 180
    temperature: float = 0.1
    max_output_tokens: int = 256
    require_allow_action: bool = True
    allow_reject_below_probability_delta: float = 0.03


@dataclass
class AutoLoopConfig:
    max_iterations: int = 6
    max_stale_iterations: int = 3
    sleep_seconds_between_iterations: int = 60
    mutation_sequence: list[str] = field(
        default_factory=lambda: [
            "base",
            "broader_trend_grid",
            "narrower_universe",
            "wider_universe",
            "stricter_costs",
            "higher_candidate_bar",
        ]
    )


@dataclass
class StrategySearchConfig:
    trend_ema: dict[str, list[float | int]] = field(default_factory=dict)
    trend_pullback: dict[str, list[float | int]] = field(default_factory=dict)
    breakout: dict[str, list[float | int]] = field(default_factory=dict)
    vol_squeeze: dict[str, list[float | int]] = field(default_factory=dict)
    mean_reversion: dict[str, list[float | int]] = field(default_factory=dict)


@dataclass
class Settings:
    paths: PathConfig = field(default_factory=PathConfig)
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    data: DataConfig = field(default_factory=DataConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)
    labeling: LabelingConfig = field(default_factory=LabelingConfig)
    research: ResearchConfig = field(default_factory=ResearchConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    portfolio: PortfolioConfig = field(default_factory=PortfolioConfig)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)
    deployment: DeploymentConfig = field(default_factory=DeploymentConfig)
    paper: PaperConfig = field(default_factory=PaperConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    local_llm: LocalLLMConfig = field(default_factory=LocalLLMConfig)
    autoloop: AutoLoopConfig = field(default_factory=AutoLoopConfig)
    strategy_search: StrategySearchConfig = field(default_factory=StrategySearchConfig)
    project_root: Path = field(default_factory=lambda: Path.cwd())

    def resolve_path(self, value: str) -> Path:
        return (self.project_root / value).resolve()

    @property
    def data_root(self) -> Path:
        return self.resolve_path(self.paths.data_root)

    @property
    def cache_root(self) -> Path:
        return self.resolve_path(self.paths.cache_root)

    @property
    def market_data_root(self) -> Path:
        return self.resolve_path(self.paths.market_data_root)

    @property
    def artifact_root(self) -> Path:
        return self.resolve_path(self.paths.artifact_root)

    @property
    def registry_db(self) -> Path:
        return self.resolve_path(self.paths.registry_db)

    @property
    def deployment_bundle_path(self) -> Path:
        return self.resolve_path(self.deployment.bundle_path)

    @property
    def deployment_manifest_path(self) -> Path:
        return self.resolve_path(self.deployment.manifest_path)

    @property
    def paper_state_db(self) -> Path:
        return self.resolve_path(self.paper.state_db)

    @property
    def paper_log_path(self) -> Path:
        return self.resolve_path(self.paper.log_path)

    def ensure_directories(self) -> None:
        for path in [
            self.data_root,
            self.cache_root,
            self.market_data_root,
            self.artifact_root,
            self.registry_db.parent,
            self.deployment_bundle_path.parent,
            self.deployment_manifest_path.parent,
            self.paper_state_db.parent,
            self.paper_log_path.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    @classmethod
    def load(cls, config_path: str | Path) -> "Settings":
        path = Path(config_path).resolve()
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        settings = dataclass_from_dict(cls, raw)
        settings.project_root = path.parent.parent.resolve()
        settings.ensure_directories()
        return settings


def dataclass_from_dict(cls: type[T], values: dict[str, Any]) -> T:
    kwargs: dict[str, Any] = {}
    type_hints = get_type_hints(cls)
    for field_def in fields(cls):
        if field_def.name not in values:
            continue
        type_hint = type_hints.get(field_def.name, field_def.type)
        kwargs[field_def.name] = _convert_value(type_hint, values[field_def.name])
    return cls(**kwargs)


def _convert_value(type_hint: Any, value: Any) -> Any:
    origin = get_origin(type_hint)
    if origin is list:
        item_type = get_args(type_hint)[0]
        return [_convert_value(item_type, item) for item in value]
    if origin is dict:
        return value
    if is_dataclass_type(type_hint) and isinstance(value, dict):
        return dataclass_from_dict(type_hint, value)
    if type_hint is Path:
        return Path(value)
    return value


def is_dataclass_type(candidate: Any) -> bool:
    try:
        return is_dataclass(candidate)
    except TypeError:
        return False
