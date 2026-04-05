# newYJT Structure Map

`newYJT` now uses a role-based layout for the main application code.

## Directories

- `model/`
  - Model registry and model-related metadata.
  - Current FreqAI model/strategy names are centralized in `model/registry.py`.

- `logic/`
  - Environment parsing, runtime config rendering, supervisor/orchestration, and status aggregation.
  - This layer coordinates how the app runs.

- `trade/`
  - Simulation/live-preflight/trade-shadow code and exchange-facing trade helpers.
  - Includes `binanceTrade.py`, preflight checks, and trade loop code.

- `templates/`
  - HTML templates for the dashboard UI.
  - Main dashboard template is `templates/index.html`.

- `static/`
  - Static frontend assets such as CSS.
  - Main stylesheet is `static/style.css`.

## Compatibility

Older entry points are still preserved:

- `scripts/*.py`
- root `binanceTrade.py`
- `strategies/DynamicStakeFreqaiStrategy.py`
- root `index.html`

These act as thin compatibility wrappers so existing commands still work while the real implementation lives in the new directories.
