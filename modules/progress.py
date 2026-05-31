"""
Broker de progreso en memoria para feedback live (Capa A, estilo ComfyUI).

La orquestación es fire-and-forget dentro del mismo proceso uvicorn, así que un
pub/sub en memoria por `search_id` alcanza: cada paso del pipeline publica un
evento y el endpoint SSE (`/events/search/{id}`) lo transmite al navegador.

Diseño clave:
  - `publish` es SÍNCRONO y seguro sin suscriptores (solo acumula historial),
    para no romper la orquestación ni los tests existentes.
  - `subscribe` siembra la cola con el historial ANTES de registrarse (en el
    mismo tick síncrono), de modo que un cliente que llega tarde no pierde
    eventos ya emitidos.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from collections import defaultdict

TERMINAL = {"completed", "error"}
PIPELINE = "_pipeline"


class ProgressBroker:
    def __init__(self, max_history: int = 300):
        self._subs: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self._history: dict[int, list[dict]] = defaultdict(list)
        self._max = max_history

    def publish(self, search_id: int, event: dict) -> None:
        hist = self._history[search_id]
        hist.append(event)
        if len(hist) > self._max:
            del hist[: len(hist) - self._max]
        for q in list(self._subs.get(search_id, ())):
            q.put_nowait(event)

    def history(self, search_id: int) -> list[dict]:
        return list(self._history.get(search_id, ()))

    def is_terminal(self, event: dict) -> bool:
        return event.get("node") == PIPELINE and event.get("status") in TERMINAL

    async def subscribe(self, search_id: int, replay: bool = True):
        """Async-generator de eventos: primero el historial, luego los vivos."""
        q: asyncio.Queue = asyncio.Queue()
        if replay:
            for ev in self._history.get(search_id, []):
                q.put_nowait(ev)
        self._subs[search_id].add(q)          # registrar DESPUÉS de sembrar (mismo tick)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs[search_id].discard(q)

    def clear(self, search_id: int) -> None:
        self._history.pop(search_id, None)
        self._subs.pop(search_id, None)


broker = ProgressBroker()


def publish(search_id: int, node: str, status: str, **extra) -> None:
    """Atajo: arma el evento con timestamp y lo publica en el broker global."""
    event = {"node": node, "status": status, "ts": dt.datetime.now(dt.UTC).isoformat()}
    event.update(extra)
    broker.publish(search_id, event)
