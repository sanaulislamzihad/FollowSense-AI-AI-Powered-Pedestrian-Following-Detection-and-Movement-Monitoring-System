"""WebSocket hub: pushes alerts and job progress to every connected dashboard."""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class RealtimeHub:
    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def _broadcast(self, text: str) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_text(text)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    def publish(self, message: dict) -> None:
        """Thread-safe: may be called from processing worker threads."""
        if self.loop is None or not self.clients:
            return
        text = json.dumps(message, default=str)
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(text), self.loop)
        except RuntimeError:
            log.debug("event loop closed, dropping realtime message")


hub = RealtimeHub()
