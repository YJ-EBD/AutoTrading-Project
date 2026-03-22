# Architecture

## Layers

1. `exchange`
   - request-weight budgeting
   - official metadata discovery
   - retry and cool-down handling
   - disk-backed cache
   - research subset selection with optional base-asset deduplication
   - guardrails for minimum history and minimum price to avoid unstable microstructure
2. `data`
   - 15m kline ingestion
   - quality checks
   - parquet storage
   - websocket design hooks
3. `strategies`
   - parameterized Pine-style strategy templates
   - Pine text emission
   - Python signal generation
   - semantic parity tests
4. `backtest`
   - realistic order simulation
   - leverage-aware returns
   - account-level returns scaled by configurable capital-at-risk per trade
   - stop, target, horizon, and liquidation handling
5. `labeling` and `features`
   - event construction
   - meta-label targets
   - point-in-time features only
6. `ml`
   - expanding-window walk-forward splits
   - calibration
   - threshold search
   - robustness diagnostics
7. `portfolio`
   - survivor selection
   - exposure constraints
   - aggregate portfolio evaluation
8. `reporting`
   - reproducible artifacts
   - markdown, json, and csv reports
9. `orchestration`
   - experiment lifecycle
   - research loop
   - weekly refresh entrypoints

## Reproducibility

- Centralized YAML configuration.
- SQLite experiment registry with config snapshots.
- Deterministic seeds for model training and sampling.
- Artifact directory per experiment for reports, datasets, and metrics.

## Validation design

- No random shuffling.
- Expanding-window train, calibration, threshold, and test splits.
- Strict separation between threshold tuning and final test evaluation.
- Robustness rejection based on fold consistency, threshold stability, cost stress, and Monte Carlo trade perturbation.
