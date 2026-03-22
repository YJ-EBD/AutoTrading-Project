from __future__ import annotations

import argparse
import asyncio
import json

from .config import Settings
from .data.ingestion import KlineIngestionService
from .exchange.client import BinancePublicClient, ClientDependencies
from .exchange.rate_limit import RateBudgetManager
from .exchange.universe import UniverseManager
from .ml.deployment import build_deployment_bundle
from .orchestration.auto_loop import run_autonomous_loop, run_continuous_loop
from .orchestration.research_loop import ResearchLoop
from .orchestration.weekly_refresh import run_weekly_refresh
from .paper.dashboard import serve_dashboard
from .paper.runtime import PaperTradingRuntime
from .storage import DiskCache
from .utils import configure_logging


def build_clients(settings: Settings) -> tuple[BinancePublicClient, UniverseManager, KlineIngestionService]:
    cache = DiskCache(settings.cache_root)
    rate_budget = RateBudgetManager(settings.exchange)
    client = BinancePublicClient(ClientDependencies(settings=settings, cache=cache, rate_budget=rate_budget))
    return client, UniverseManager(settings, client), KlineIngestionService(settings, client)


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance quant research CLI")
    parser.add_argument(
        "command",
        choices=[
            "discover-universe",
            "backfill",
            "run-research",
            "weekly-refresh",
            "auto-loop",
            "continuous-loop",
            "build-deployment",
            "paper-runtime",
            "serve-paper",
        ],
    )
    parser.add_argument("--config", default="configs/base.yaml")
    args = parser.parse_args()

    configure_logging()
    settings = Settings.load(args.config)

    if args.command == "discover-universe":
        _, universe_manager, _ = build_clients(settings)
        universe = universe_manager.discover(settings.artifact_root / "latest")
        print(universe.to_json(orient="records"))
        return
    if args.command == "backfill":
        _, universe_manager, ingestion = build_clients(settings)
        universe = universe_manager.discover(settings.artifact_root / "latest")
        data = ingestion.backfill_many(universe["symbol"].tolist(), artifact_dir=settings.artifact_root / "latest")
        summary = {symbol: len(frame) for symbol, frame in data.items()}
        print(json.dumps(summary, indent=2))
        return
    if args.command == "run-research":
        result = ResearchLoop(settings).run()
        print(json.dumps(result, indent=2, default=str))
        return
    if args.command == "auto-loop":
        result = run_autonomous_loop(settings)
        print(json.dumps(result, indent=2, default=str))
        return
    if args.command == "continuous-loop":
        result = run_continuous_loop(settings)
        print(json.dumps(result, indent=2, default=str))
        return
    if args.command == "build-deployment":
        bundle = build_deployment_bundle(settings)
        print(json.dumps(bundle.manifest.__dict__, indent=2, default=str))
        return
    if args.command == "paper-runtime":
        runtime = PaperTradingRuntime(settings)
        asyncio.run(runtime.serve())
        return
    if args.command == "serve-paper":
        serve_dashboard(settings, start_runtime=True)
        return
    result = run_weekly_refresh(settings)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
