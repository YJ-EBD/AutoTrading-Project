# Hydra-Engine Adaptation

This project reviewed `sinmb79/Hydra-Engine` and adapted the parts that fit the current Binance paper-trading runtime without forcing a full architectural rewrite.

Applied patterns:

- Local operational state persisted in the runtime database instead of an external state store.
- Health endpoint for runtime, stream, and kill-switch visibility.
- Manual and automatic kill switch for emergency paper-position shutdown and new-entry blocking.
- Optional API-key protection for state-changing dashboard API routes.

Hydra-inspired behaviors now present here:

- `GET /health` reports runtime health with uptime and degraded status when the stream or kill switch is unhealthy.
- `POST /api/kill-switch/activate` closes active paper positions and blocks new entries.
- `POST /api/kill-switch/deactivate` clears the block and lets runtime resume normal entry evaluation.
- Automatic kill switch can activate when realized daily paper loss breaches the configured threshold.

Not ported directly:

- Hydra's Redis state store and exchange-wide live order cancel flow.
- Telegram notification layer.
- Full Hydra process topology and Docker profile system.

Reason:

This repository already has a SQLite-backed runtime state system, its own research loop, and a paper-only execution model. The adaptation therefore focused on operational controls, observability, and safety rather than copying Hydra's entire project layout.
