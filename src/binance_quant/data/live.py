from __future__ import annotations

import asyncio
import inspect
import json
import logging
import random
from collections.abc import AsyncIterator
from typing import Any, Callable

import websockets

from ..config import Settings


LOGGER = logging.getLogger(__name__)


class CombinedKlineStreamClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def build_stream_url(self, symbols: list[str], interval: str) -> str:
        streams = "/".join(f"{symbol.lower()}@kline_{interval}" for symbol in symbols)
        return f"{self.settings.exchange.base_ws_url}/stream?streams={streams}"

    async def stream_klines(
        self,
        symbols: list[str],
        interval: str,
        status_handler: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> AsyncIterator[dict]:
        url = self.build_stream_url(symbols, interval)
        loop = asyncio.get_running_loop()
        rotate_after = self.settings.exchange.websocket_rotate_hours * 3600
        base_reconnect_delay = self.settings.exchange.websocket_reconnect_delay_seconds
        reconnect_delay = base_reconnect_delay
        max_reconnect_delay = self.settings.exchange.websocket_reconnect_delay_max_seconds
        reconnect_backoff = self.settings.exchange.websocket_reconnect_backoff_multiplier
        reconnect_jitter = self.settings.exchange.websocket_reconnect_jitter_seconds
        receive_timeout = self.settings.exchange.websocket_receive_timeout_seconds
        stall_pong_timeout = self.settings.exchange.websocket_stall_pong_timeout_seconds
        while True:
            started = loop.time()
            await _emit_status(
                status_handler,
                "connecting",
                {"url": url, "symbol_count": len(symbols), "interval": interval},
            )
            try:
                connect_kwargs: dict[str, Any] = {
                    "open_timeout": self.settings.exchange.websocket_open_timeout_seconds,
                    "close_timeout": self.settings.exchange.websocket_close_timeout_seconds,
                    "max_queue": self.settings.exchange.websocket_max_queue,
                }
                if self.settings.exchange.websocket_disable_builtin_ping:
                    connect_kwargs["ping_interval"] = None
                    connect_kwargs["ping_timeout"] = None
                else:
                    connect_kwargs["ping_interval"] = self.settings.exchange.websocket_ping_interval_seconds
                    connect_kwargs["ping_timeout"] = self.settings.exchange.websocket_ping_timeout_seconds
                async with websockets.connect(url, **connect_kwargs) as socket:
                    reconnect_delay = base_reconnect_delay
                    await _emit_status(status_handler, "connected", {"url": url})
                    while True:
                        if loop.time() - started >= rotate_after:
                            LOGGER.info("Rotating websocket connection after %s seconds", rotate_after)
                            await _emit_status(
                                status_handler,
                                "rotating",
                                {"url": url, "rotate_after_seconds": rotate_after},
                            )
                            break
                        try:
                            message = await asyncio.wait_for(socket.recv(), timeout=receive_timeout)
                        except asyncio.TimeoutError:
                            await _emit_status(
                                status_handler,
                                "stalled",
                                {"url": url, "receive_timeout_seconds": receive_timeout},
                            )
                            pong = await socket.ping()
                            await asyncio.wait_for(pong, timeout=stall_pong_timeout)
                            await _emit_status(
                                status_handler,
                                "heartbeat_ok",
                                {"url": url, "stall_pong_timeout_seconds": stall_pong_timeout},
                            )
                            continue
                        await _emit_status(status_handler, "message", {"url": url})
                        yield json.loads(message)
            except Exception as exc:  # pragma: no cover - network instability is handled operationally
                LOGGER.warning("Websocket stream interrupted: %s", exc)
                await _emit_status(status_handler, "interrupted", {"url": url, "error": str(exc)})
                delay_seconds = min(reconnect_delay, max_reconnect_delay) + random.uniform(0.0, reconnect_jitter)
                await _emit_status(
                    status_handler,
                    "retrying",
                    {
                        "url": url,
                        "retry_in_seconds": delay_seconds,
                        "base_retry_in_seconds": reconnect_delay,
                    },
                )
                await asyncio.sleep(delay_seconds)
                reconnect_delay = min(reconnect_delay * reconnect_backoff, max_reconnect_delay)


async def _emit_status(
    handler: Callable[[str, dict[str, Any]], Any] | None,
    event: str,
    payload: dict[str, Any],
) -> None:
    if handler is None:
        return
    result = handler(event, payload)
    if inspect.isawaitable(result):
        await result
