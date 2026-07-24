"""memory/queue.py — cola async de escritura de la memoria (V2-002 · T45).

TODAS las escrituras entran por aquí. Un **único consumidor** drena la cola y llama al writer (`memory/
writer.py`) → cero colisiones de escritura; los lectores (retriever/state) van directos en WAL sin bloquear.
La inserción NO es urgente: puede tardar (calcula embeddings locales), pero nunca bloquea la ruta caliente.

**Loop-agnóstico** (mismo patrón que `bus/` y `runtime.locked_ask`): los escritores pueden vivir en otro
hilo/loop (job-thread de LiveKit, callbacks de subprocess). `submit()` encola de forma segura desde cualquier
hilo — si es el loop del consumidor, `put_nowait`; si no, `call_soon_threadsafe`. Si aún no hay consumidor
arrancado (p. ej. tests/standalone), `submit()` aplica la escritura **en línea** (best-effort) para no perderla.

Cada item = `(op, args, kwargs, future|None)`. `op` mapea a `writer.OPS`. Si se pasa un `future`, se resuelve
con el resultado (lo usa `api.write` cuando el llamador quiere el id de vuelta).
"""
import asyncio
import threading
from typing import Any

from . import writer as _writer


class MemoryQueue:
    def __init__(self):
        self._q: asyncio.Queue | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._lock = threading.Lock()
        self._running = False

    # ── ciclo de vida ──────────────────────────────────────────────────────────────────────────────────
    async def start(self):
        """Arranca el consumidor en el loop actual. Idempotente."""
        with self._lock:
            if self._running:
                return
            self._loop = asyncio.get_running_loop()
            self._q = asyncio.Queue()
            self._running = True
            self._task = self._loop.create_task(self._consume())

    async def stop(self, drain: bool = True):
        """Para el consumidor. Si `drain`, procesa lo pendiente antes de salir."""
        if not self._running:
            return
        if drain and self._q is not None:
            await self._q.join()
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None

    async def join(self):
        """Espera a que la cola se vacíe (tests: submit → join → query)."""
        if self._q is not None:
            await self._q.join()

    # ── consumidor único ───────────────────────────────────────────────────────────────────────────────
    async def _consume(self):
        assert self._q is not None
        while True:
            op, args, kwargs, fut = await self._q.get()
            try:
                result = self._apply(op, args, kwargs)
                if fut is not None and not fut.done():
                    fut.get_loop().call_soon_threadsafe(fut.set_result, result)
                # Observabilidad en vivo (V2-014): re-emite `memory.updated` con el id REAL una vez la
                # escritura async terminó (el emit de `api.write` es previo al insert y no tiene id todavía).
                # Así el visor de memoria puede TEÑIR el nodo exacto (verde=alta, ámbar=sobrescritura).
                self._emit_written(op, args, result)
            except Exception as e:  # una escritura mala NUNCA tumba al consumidor
                if fut is not None and not fut.done():
                    fut.get_loop().call_soon_threadsafe(fut.set_exception, e)
            finally:
                self._q.task_done()

    @staticmethod
    def _emit_written(op: str, args: tuple, result: Any) -> None:
        """Señal fina post-escritura con el id afectado (best-effort, nunca rompe el consumidor)."""
        try:
            if op == "write" and result is not None:
                payload = {"op": "write", "id": int(result)}
            elif op == "supersede" and args:
                payload = {"op": "supersede", "id": int(args[0])}
            else:
                return
            import bus
            bus.emit_sync("memory.updated", payload)
        except Exception:
            pass

    @staticmethod
    def _apply(op: str, args: tuple, kwargs: dict) -> Any:
        fn = _writer.OPS.get(op)
        if fn is None:
            raise ValueError(f"op de memoria desconocida: {op!r}")
        return fn(*args, **kwargs)

    # ── encolar (desde cualquier hilo) ─────────────────────────────────────────────────────────────────
    def submit(self, op: str, *args, future: asyncio.Future | None = None, **kwargs):
        """Encola una escritura. Loop-agnóstico. Si no hay consumidor, aplica en línea (best-effort)."""
        item = (op, args, kwargs, future)
        if not self._running or self._q is None or self._loop is None:
            # sin consumidor: aplicar en línea para no perder la escritura (standalone/tests).
            try:
                res = self._apply(op, args, kwargs)
                if future is not None and not future.done():
                    future.get_loop().call_soon_threadsafe(future.set_result, res)
            except Exception as e:
                if future is not None and not future.done():
                    future.get_loop().call_soon_threadsafe(future.set_exception, e)
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._q.put_nowait(item)
        else:
            self._loop.call_soon_threadsafe(self._q.put_nowait, item)


# singleton de módulo
_QUEUE = MemoryQueue()


def get_queue() -> MemoryQueue:
    return _QUEUE
