"""nucleo/workers/codex_session.py — backend `CodexSession` (adaptador, V2-038).

STUB HONESTO: la agnosticidad (O1) exige que el registro pueda devolver un backend Codex sin que el resto del
sistema cambie. Cuando el CLI de Codex con transporte streaming esté validado, este adaptador traduce su protocolo
nativo a `WorkerEvent` (igual que `ClaudeCodeSession` hace con stream-json). Hasta entonces, si se selecciona,
emite un error CLARO y cierra — nunca finge trabajar. Así el punto de extensión existe y está documentado.
"""
from __future__ import annotations

import asyncio

from .base import WorkerBackend, WorkerEvent, WorkerSpec


class CodexSession(WorkerBackend):
    name = "codex"

    def __init__(self):
        self._q: asyncio.Queue[WorkerEvent] = asyncio.Queue()
        self._task_id = ""
        self._done = False

    async def start(self, prompt: str, *, spec: "WorkerSpec") -> None:
        self._task_id = spec.task_id or ""
        await self._q.put(WorkerEvent(task_id=self._task_id, type="error", backend=self.name,
                                      data={"message": "backend 'codex' aún no implementado — usa claude_code",
                                            "fatal": True}))
        await self._q.put(WorkerEvent(task_id=self._task_id, type="done", backend=self.name))
        self._done = True

    async def send(self, text: str) -> None:
        return

    async def events(self):
        while True:
            ev = await self._q.get()
            yield ev
            if ev.type == "done":
                return

    async def stop(self, *, grace: float = 3.0) -> None:
        self._done = True

    @property
    def alive(self) -> bool:
        return not self._done
