"""bus/ — Sistema Nervioso de zaelar v2 «Colmena» (EPIC-v2-colmena, INI V2-001).

Pub/sub de señales **in-process** (asyncio) — la generalización de `voice/observer.py`. Transporte
**HÍBRIDO**: la ruta caliente de la voz sigue por llamada directa (latencia); el bus es para señales
async/fan-out (memoria actualizada, widgets, escalados, ticks del loop). **NADA de Kafka/broker** — todo
vive dentro de este proceso.

Contrato público:
  - `publish(topic, payload)`      — corutina; entrega `payload` a los suscriptores cuyo patrón casa `topic`.
  - `emit_sync(topic, payload)`    — versión **loop-agnóstica** para hilos que NO son el loop principal
                                     (p. ej. el job-thread de LiveKit), igual patrón que `runtime.locked_ask`.
  - `subscribe(pattern="*")`       — devuelve una `Subscription` (async-iterator + `.get()`), sin bloquear.
  - `unsubscribe(sub)`             — cierra una suscripción (equivalente a `sub.close()`).
  - `add_sink(fn)` / `remove_sink` — sink SÍNCRONO llamado en CADA evento (lo usa `bus/log.py` para el log
                                     durable en SQLite; loop-agnóstico, corre en el hilo que publica).

**Loop-agnóstico**: cada `Subscription` recuerda el event-loop en el que se creó; la entrega usa
`loop.call_soon_threadsafe` cuando el publicador corre en OTRO hilo/loop (arregla, de paso, la entrega
cross-loop que el viejo `observer` hacía con `put_nowait` a pelo). Los sinks se invocan síncronos en el
hilo publicador — deben ser baratos y no bloquear (el de SQLite usa su propia conexión + lock).

Topics iniciales (convención `dominio.suceso`, wildcard estilo fnmatch): `memory.updated`, `widget.*`,
`brain.*`, `connector.msg`, `loop.tick`, `escalate.*`, `observer` (puente SSE del frontend).
"""
import asyncio
import fnmatch
import threading
import time
from typing import Any, Callable

__all__ = [
    "Subscription",
    "publish",
    "emit_sync",
    "subscribe",
    "unsubscribe",
    "add_sink",
    "remove_sink",
    "reset",
]


def now_ms() -> float:
    return time.time() * 1000.0


class Subscription:
    """Una suscripción viva a un patrón de topic. Es un async-iterator (`async for ev in sub`) y además
    expone `.get()` (compat con el viejo `observer.subscribe()` que devolvía una `asyncio.Queue`)."""

    def __init__(self, bus: "Bus", pattern: str, maxsize: int = 0):
        self._bus = bus
        self.pattern = pattern
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None  # creada fuera de un loop (raro); se resolverá en el primer get()
        self._closed = False

    # entrega loop-safe: la llama el bus desde el hilo/loop del publicador.
    def _deliver(self, ev: Any):
        if self._closed:
            return
        loop = self._loop
        if loop is not None and loop.is_running():
            try:
                running = asyncio.get_running_loop()
            except RuntimeError:
                running = None
            if running is loop:
                # mismo loop → encolar directo
                try:
                    self.queue.put_nowait(ev)
                except asyncio.QueueFull:
                    pass
            else:
                # otro hilo/loop → cruzar de forma segura
                try:
                    loop.call_soon_threadsafe(self._safe_put, ev)
                except RuntimeError:
                    pass
        else:
            # sin loop conocido: mejor esfuerzo
            try:
                self.queue.put_nowait(ev)
            except Exception:
                pass

    def _safe_put(self, ev: Any):
        try:
            self.queue.put_nowait(ev)
        except asyncio.QueueFull:
            pass

    async def get(self) -> Any:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return await self.queue.get()

    def __aiter__(self):
        return self

    async def __anext__(self) -> Any:
        if self._closed and self.queue.empty():
            raise StopAsyncIteration
        return await self.get()

    def close(self):
        self._closed = True
        self._bus._remove(self)

    # context-manager azúcar
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


class Bus:
    """El bus in-process. Normalmente se usa el singleton de módulo (`publish`/`subscribe`/…), pero la clase
    es instanciable para tests aislados."""

    def __init__(self):
        self._subs: list[Subscription] = []
        self._sinks: list[Callable[[dict], None]] = []
        self._lock = threading.Lock()  # protege las listas (se tocan desde varios hilos)

    # ── suscripción ───────────────────────────────────────────────────────────────────────────────────
    def subscribe(self, pattern: str = "*", maxsize: int = 0) -> Subscription:
        sub = Subscription(self, pattern, maxsize=maxsize)
        with self._lock:
            self._subs.append(sub)
        return sub

    def unsubscribe(self, sub: Subscription):
        sub.close()

    def _remove(self, sub: Subscription):
        with self._lock:
            if sub in self._subs:
                self._subs.remove(sub)

    # ── sinks (log durable) ───────────────────────────────────────────────────────────────────────────
    def add_sink(self, fn: Callable[[dict], None]):
        with self._lock:
            if fn not in self._sinks:
                self._sinks.append(fn)

    def remove_sink(self, fn: Callable[[dict], None]):
        with self._lock:
            if fn in self._sinks:
                self._sinks.remove(fn)

    # ── publicación ───────────────────────────────────────────────────────────────────────────────────
    def _dispatch(self, topic: str, payload: Any):
        """Reparto síncrono (no bloquea, solo encola / llama sinks). Compartido por publish + emit_sync."""
        with self._lock:
            subs = list(self._subs)
            sinks = list(self._sinks)
        for sub in subs:
            if _match(sub.pattern, topic):
                sub._deliver(payload)
        # sinks: log durable + cualquier consumidor síncrono. El evento del sink SÍ lleva metadatos.
        if sinks:
            rec = {"topic": topic, "ts_ms": now_ms(), "payload": payload}
            for fn in sinks:
                try:
                    fn(rec)
                except Exception:
                    pass

    async def publish(self, topic: str, payload: Any = None):
        """Publica un evento. Async por contrato, pero el reparto es no-bloqueante (solo encola)."""
        self._dispatch(topic, payload)

    def emit_sync(self, topic: str, payload: Any = None):
        """Publica desde CUALQUIER hilo/loop (job-thread de LiveKit, subprocess callbacks…). Loop-agnóstico:
        cada suscriptor recibe la entrega en SU loop vía call_soon_threadsafe."""
        self._dispatch(topic, payload)

    def reset(self):
        """Vacía suscriptores y sinks (para tests)."""
        with self._lock:
            for s in self._subs:
                s._closed = True
            self._subs.clear()
            self._sinks.clear()


def _match(pattern: str, topic: str) -> bool:
    if pattern == "*" or pattern == topic:
        return True
    return fnmatch.fnmatchcase(topic, pattern)


# ── singleton de módulo ─────────────────────────────────────────────────────────────────────────────────
_BUS = Bus()


async def publish(topic: str, payload: Any = None):
    await _BUS.publish(topic, payload)


def emit_sync(topic: str, payload: Any = None):
    _BUS.emit_sync(topic, payload)


def subscribe(pattern: str = "*", maxsize: int = 0) -> Subscription:
    return _BUS.subscribe(pattern, maxsize=maxsize)


def unsubscribe(sub: Subscription):
    _BUS.unsubscribe(sub)


def add_sink(fn: Callable[[dict], None]):
    _BUS.add_sink(fn)


def remove_sink(fn: Callable[[dict], None]):
    _BUS.remove_sink(fn)


def reset():
    _BUS.reset()


def get_bus() -> Bus:
    return _BUS
