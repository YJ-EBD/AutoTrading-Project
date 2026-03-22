from __future__ import annotations

import asyncio
import inspect
import json
import logging
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
        rotate_after = self.settings.exchange.websocket_rotate_hours * 3600
        reconnect_delay = self.settings.exchange.websocket_reconnect_delay_seconds
        while True:
            started = asyncio.get_event_loop().time()
            await _emit_status(
                status_handler,
                "connecting",
                {"url": url, "symbol_count": len(symbols), "interval": interval},
            )
            try:
                async with websockets.connect(
                    url,
                    ping_interval=self.settings.exchange.websocket_ping_interval_seconds,
                    ping_timeout=self.settings.exchange.websocket_ping_timeout_seconds,
                    open_timeout=self.settings.exchange.websocket_open_timeout_seconds,
                    close_timeout=self.settings.exchange.websocket_close_timeout_seconds,
                ) as socket:
                    await _emit_status(status_handler, "connected", {"url": url})
                    while True:
                        if asyncio.get_event_loop().time() - started >= rotate_after:
                            LOGGER.info("Rotating websocket connection after %s seconds", rotate_after)
                            await _emit_status(
                                status_handler,
                                "rotating",
                                {"url": url, "rotate_after_seconds": rotate_after},
                            )
                            break
                        message = await socket.recv()
                        await _emit_status(status_handler, "message", {"url": url})
                        yield json.loads(message)
            except Exception as exc:  # pragma: no cover - network instability is handled operationally
                LOGGER.warning("Websocket stream interrupted: %s", exc)
                await _emit_status(status_handler, "interrupted", {"url": url, "error": str(exc)})
                await _emit_status(
                    status_handler,
                    "retrying",
                    {"url": url, "retry_in_seconds": reconnect_delay},
                )
                await asyncio.sleep(reconnect_delay)


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
