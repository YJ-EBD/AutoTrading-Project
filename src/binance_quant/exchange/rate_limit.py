from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from ..config import ExchangeConfig


@dataclass
class RequestTelemetry:
    endpoint: str
    bucket: str
    weight: int
    status_code: int
    duration_seconds: float
    used_weight_1m: int | None = None


class RateBudgetManager:
    def __init__(self, config: ExchangeConfig):
        self.config = config
        self.lock = threading.Lock()
        self.global_window: deque[tuple[float, int]] = deque()
        self.bucket_windows: dict[str, deque[tuple[float, int]]] = defaultdict(deque)
        self.cooldown_until: float = 0.0
        self.telemetry: list[RequestTelemetry] = []

    def acquire(self, weight: int, bucket: str) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self._prune(now)
                if now < self.cooldown_until:
                    sleep_for = self.cooldown_until - now
                else:
                    global_used = sum(item_weight for _, item_weight in self.global_window)
                    bucket_used = sum(item_weight for _, item_weight in self.bucket_windows[bucket])
                    bucket_cap = self.config.request_weight_budgets.get(bucket, self.config.request_weight_cap_per_minute)
                    if (
                        global_used + weight <= self.config.request_weight_cap_per_minute
                        and bucket_used + weight <= bucket_cap
                    ):
                        self.global_window.append((now, weight))
                        self.bucket_windows[bucket].append((now, weight))
                        return
                    next_global = self.global_window[0][0] + 60 if self.global_window else now + 1
                    next_bucket = self.bucket_windows[bucket][0][0] + 60 if self.bucket_windows[bucket] else now + 1
                    sleep_for = max(min(next_global, next_bucket) - now, 0.1)
            time.sleep(min(sleep_for, 1.0))

    def set_cooldown(self, seconds: float) -> None:
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, time.monotonic() + seconds)

    def record_telemetry(self, item: RequestTelemetry) -> None:
        with self.lock:
            self.telemetry.append(item)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {
                "requests": len(self.telemetry),
                "cooldown_until": self.cooldown_until,
                "by_bucket": {
                    bucket: sum(weight for _, weight in queue)
                    for bucket, queue in self.bucket_windows.items()
                },
            }

    def _prune(self, now: float) -> None:
        while self.global_window and now - self.global_window[0][0] > 60:
            self.global_window.popleft()
        for queue in self.bucket_windows.values():
            while queue and now - queue[0][0] > 60:
                queue.popleft()
