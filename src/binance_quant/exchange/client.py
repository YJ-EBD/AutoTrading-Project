from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from ..config import Settings
from ..storage import DiskCache
from .rate_limit import RateBudgetManager, RequestTelemetry


LOGGER = logging.getLogger(__name__)


@dataclass
class ClientDependencies:
    settings: Settings
    cache: DiskCache
    rate_budget: RateBudgetManager


class BinancePublicClient:
    def __init__(self, dependencies: ClientDependencies):
        self.settings = dependencies.settings
        self.cache = dependencies.cache
        self.rate_budget = dependencies.rate_budget
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "binance-quant-research/0.1"})

    def get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        bucket: str,
        weight: int,
        cache_namespace: str | None = None,
        cache_key: str | None = None,
        ttl_seconds: int | None = None,
    ) -> Any:
        params = params or {}
        if cache_namespace and cache_key and ttl_seconds:
            cached = self.cache.get(cache_namespace, cache_key, ttl_seconds)
            if cached is not None:
                return cached

        url = f"{self.settings.exchange.base_rest_url}{path}"
        attempts = self.settings.exchange.max_retry_attempts
        for attempt in range(1, attempts + 1):
            self.rate_budget.acquire(weight, bucket)
            started = time.perf_counter()
            response = None
            try:
                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.settings.exchange.request_timeout_seconds,
                )
                duration = time.perf_counter() - started
                used_weight = response.headers.get("x-mbx-used-weight-1m")
                self.rate_budget.record_telemetry(
                    RequestTelemetry(
                        endpoint=path,
                        bucket=bucket,
                        weight=weight,
                        status_code=response.status_code,
                        duration_seconds=duration,
                        used_weight_1m=int(used_weight) if used_weight and used_weight.isdigit() else None,
                    )
                )
                if response.status_code == 429:
                    self.rate_budget.set_cooldown(min(60.0, 5.0 * attempt))
                    raise requests.HTTPError("Rate limited", response=response)
                if response.status_code >= 500:
                    raise requests.HTTPError("Server error", response=response)
                response.raise_for_status()
                payload = response.json()
                if cache_namespace and cache_key:
                    self.cache.set(cache_namespace, cache_key, payload)
                return payload
            except requests.RequestException as exc:
                if attempt == attempts:
                    raise
                delay = min(
                    self.settings.exchange.max_retry_delay_seconds,
                    self.settings.exchange.base_retry_delay_seconds * (2 ** (attempt - 1)),
                )
                LOGGER.warning("Request failed for %s on attempt %s/%s: %s", path, attempt, attempts, exc)
                time.sleep(delay)
        raise RuntimeError(f"Unexpected request state for {path}")
