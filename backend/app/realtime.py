"""Le stanze WebSocket: chi è collegato a quale partita, e l'avviso «è cambiato qualcosa».

Le rotte sono sincrone e girano nel threadpool: `notify()` da lì programma l'invio
sull'event loop. Ogni connessione riceve lo stato visto dal *suo* giocatore (il
voto dell'altro resta nascosto finché non hanno votato entrambi).
"""

import asyncio
import json
import logging
from collections import defaultdict

from fastapi import WebSocket
from starlette.concurrency import run_in_threadpool

log = logging.getLogger(__name__)


class Rooms:
    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.conns: dict[str, dict[WebSocket, str | None]] = defaultdict(dict)
        self.state_for = None  # callable(code, role, online) -> dict, impostato da main

    def online(self, code: str) -> set[str]:
        return {r for r in self.conns.get(code, {}).values() if r}

    async def join(self, code: str, ws: WebSocket, role: str | None):
        self.conns[code][ws] = role
        await self.broadcast(code)

    async def leave(self, code: str, ws: WebSocket):
        self.conns.get(code, {}).pop(ws, None)
        if not self.conns.get(code):
            self.conns.pop(code, None)
        await self.broadcast(code)

    async def broadcast(self, code: str):
        conns = list(self.conns.get(code, {}).items())
        if not conns or not self.state_for:
            return
        online = self.online(code)
        cache: dict[str | None, str] = {}
        for ws, role in conns:
            if role not in cache:
                state = await run_in_threadpool(self.state_for, code, role, online)
                cache[role] = json.dumps({"type": "state", "state": state})
            try:
                await ws.send_text(cache[role])
            except Exception:
                self.conns.get(code, {}).pop(ws, None)

    def notify(self, code: str):
        """Da un thread qualsiasi: rimanda lo stato a tutti i collegati."""
        if not self.loop or self.loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.broadcast(code), self.loop)
        except RuntimeError:  # pragma: no cover - loop in chiusura
            pass


rooms = Rooms()
