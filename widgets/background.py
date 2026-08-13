"""widgets/background.py — EJECUCIÓN EN BACKGROUND de widgets con CICLO (V2-034).

Un widget no siempre trabaja solo cuando está a la vista. Algunos deben seguir vivos AUNQUE la tarjeta esté
cerrada: el de mensajería recibe mensajes de sus conectores, los tría y **escribe lo nuevo en la memoria**, de
modo que si el operador pregunta por voz "¿tengo mensajes?" zaelar responde con datos ACTUALES aunque nunca haya
abierto el widget. Esa es una capacidad de PRIMER NIVEL del sistema de widgets: **background execution con un
CICLO declarado** (cada 1s / 1m / 1h…).

## Dos formas de "correr en background" (una sola idea declarativa)

Un widget declara su ciclo en el `manifest.json`:

    "background": { "every": "1m" }          # objeto (o el atajo string "background": "1m", o segundos: 60)

  - **passive + `background`** — la forma LIGERA (nueva en V2-034): NO hay proceso propio; este planificador
    llama a `data.py:tick()` cada `every`, **fuera del camino caliente de voz** (`asyncio.to_thread`, porque
    `data.py` es síncrono stdlib). El `tick()` refresca datos (`store.save()` solo si cambian → refresco SSE de
    la tarjeta abierta, sin flood porque el save es idempotente) y **vuelca a la memoria** lo relevante
    (`memory.ingest_message`/`memory.write` con `slot` para supersede). Ideal para pollers/refrescos/volcados
    que NO necesitan una conexión viva.
  - **backed** — la forma PESADA (ya existente, `widgets/supervisor.py`): un `owner.py` con proceso propio y
    conexión viva (Chromium del navegador, conectores de mensajería). Un backed ES background por naturaleza: su
    owner se auto-agenda. Si además declara `background`, este planificador le encola un comando `"tick"` en su
    buzón cada `every` (el owner lo maneja si quiere; si no lo declara, no se le molesta — mensajería, p.ej., se
    auto-agenda y NO declara `background`).

## Invariantes

  - **Fuera del hot path.** Corre en el loop del server (lifespan, MISMO que la voz y el supervisor backed) pero
    los `tick()` passive van a un hilo (`to_thread`) → nunca bloquean el event loop ni el turno de voz.
  - **Aislamiento total.** Un `tick()` que revienta o tarda NO tumba la voz, ni otro widget, ni el planificador:
    se captura, se traza (`observer`, kind `background`) y se sigue. Solape evitado por widget (si el tick
    anterior sigue corriendo, se salta ese ciclo).
  - **Periodo mínimo = 1s.** `every` se normaliza a segundos (≥1).
"""
from __future__ import annotations

import asyncio
import importlib
import re
import time

from loguru import logger

from . import runtime

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_tasks: dict[str, asyncio.Task] = {}       # wid -> tarea periódica supervisada
_inflight: set[str] = set()                # wids cuyo tick sigue corriendo (evita solape)


def parse_period(v) -> int | None:
    """Normaliza una especificación de ciclo a SEGUNDOS (mínimo 1). Acepta int/float (segundos), un dict
    `{"every": …}`, o un string `"90"`, `"30s"`, `"5m"`, `"1h"`, `"1d"`. None si no es válida."""
    if isinstance(v, dict):
        v = v.get("every")
    if isinstance(v, bool):                # bool es subtipo de int: descártalo explícitamente
        return None
    if isinstance(v, (int, float)):
        return max(1, int(v))
    if isinstance(v, str):
        m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", v.lower())
        if m:
            return max(1, int(m.group(1)) * _UNITS.get(m.group(2) or "s", 1))
    return None


def background_period(w: dict) -> int | None:
    """El ciclo (segundos) declarado por el manifest de un widget, o None si no corre en background."""
    return parse_period(w.get("background")) if w.get("background") is not None else None


def _emit(label: str, wid: str, text: str = "") -> None:
    try:
        from voice.observer import emit
        emit("background", label, text=(f"{wid}: {text}" if text else wid), extra={"id": wid})
    except Exception:
        pass


class TickCtx:
    """Contexto que el planificador pasa a `tick(ctx)` — la capa SANCIONADA para que un widget passive vuelque a
    la MEMORIA sin importar el core en su data.py (que es stdlib-only por diseño; el gate del generador lo exige).
    Espejo del `ctx` de `widget.js`. Todo best-effort: un fallo de escritura no rompe el tick."""

    def __init__(self, wid: str):
        self.widget_id = wid

    def remember(self, text: str, *, slot: str | None = None, kind: str = "note",
                 importance: float = 0.4, level: str = "mid", **extra) -> None:
        """Vuelca un dato a la memoria central. Usa `slot` (p.ej. 'weather:soria') para SUPERSEDE (el más reciente
        MANDA, no se acumula). El texto queda disponible al recall/estado → una pregunta por voz responde fresco."""
        try:
            from memory import api as memory
            meta = {"widget": self.widget_id, **(extra.pop("meta", None) or {})}
            memory.write(text, kind=kind, level=level, importance=importance, slot=slot, meta=meta, **extra)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"background[{self.widget_id}] ctx.remember falló: {e}")

    def ingest(self, source: str, entity: str, text: str, **kw):
        """Vuelca un dato ENTRANTE de una fuente (mensajería/feed…) por la vía tipada de la memoria."""
        try:
            from memory import api as memory
            return memory.ingest_message(source, entity, text, **kw)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"background[{self.widget_id}] ctx.ingest falló: {e}")
            return None

    def save(self, data: dict):
        """Persiste el store del widget (idempotente → SSE solo si cambió)."""
        from . import store
        return store.save(self.widget_id, data)


def _call_tick(wid: str):
    """Llama a `data.py:tick(ctx)` del widget (síncrono, stdlib). Corre en un hilo (`to_thread`). Acepta tanto
    `tick(ctx)` (con acceso a memoria) como `tick()` sin argumentos (compat)."""
    import inspect
    mod = importlib.import_module(f"widgets.{wid}.data")
    fn = getattr(mod, "tick", None)
    if not callable(fn):
        return None
    try:
        takes_arg = len(inspect.signature(fn).parameters) >= 1
    except (TypeError, ValueError):
        takes_arg = False
    return fn(TickCtx(wid)) if takes_arg else fn()


async def _tick_once(wid: str, kind: str) -> None:
    # V2-092: con el agente PARADO (⏻) no hay ciclos. Un «agente parado» que sigue sondeando conectores y
    # escribiendo en la memoria no está parado — y era justo lo que pasaba. El bucle NO se cancela: sigue
    # despierto contando, así que arrancar reanuda los ticks sin reconstruir el planificador.
    try:
        from nucleo import runstate
        if runstate.stopped():
            return
    except Exception:
        pass
    if wid in _inflight:                    # el ciclo anterior aún corre → salta este (no encolar trabajo lento)
        _emit("skip", wid, "tick anterior en curso")
        return
    _inflight.add(wid)
    try:
        if kind == "backed":
            from . import supervisor
            supervisor.enqueue(wid, "tick", {})     # el owner decide si lo maneja
            _emit("tick", wid, "→ owner")
        else:
            t0 = time.time()
            await asyncio.to_thread(_call_tick, wid)
            _emit("tick", wid, f"{round((time.time() - t0) * 1000)}ms")
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        _emit("error", wid, str(e))
        logger.warning(f"background[{wid}] tick falló (aislado): {e}")
    finally:
        _inflight.discard(wid)


async def _run_widget(wid: str, period: int, kind: str) -> None:
    """Bucle periódico de UN widget. Espera un poco al arranque (escalona los ticks) y luego cada `period`s."""
    await asyncio.sleep(min(period, 2.0))
    while True:
        try:
            await _tick_once(wid, kind)
        except asyncio.CancelledError:
            break
        await asyncio.sleep(period)


def start() -> None:
    """Arranca (en el lifespan del server) el planificador de background de cada widget que declara `background`.
    Idempotente. Un widget passive con `background` DEBE tener `tick()` en su data.py (si no, se omite con aviso —
    nunca rompe el arranque)."""
    for w in runtime.catalog():
        period = background_period(w)
        if not period:
            continue
        wid = w.get("id") or ""
        if not wid or wid in _tasks:
            continue
        kind = "backed" if (w.get("kind") or "passive") == "backed" else "passive"
        if kind == "passive":
            try:
                mod = importlib.import_module(f"widgets.{wid}.data")
                if not callable(getattr(mod, "tick", None)):
                    logger.warning(f"background[{wid}] declara 'background' pero data.py no tiene tick() — omitido")
                    _emit("no_tick", wid)
                    continue
            except Exception as e:  # noqa: BLE001
                logger.warning(f"background[{wid}] no se pudo importar data.py: {e}")
                continue
        _tasks[wid] = asyncio.create_task(_run_widget(wid, period, kind))
        logger.info(f"background[{wid}] cada {period}s ({kind})")
        _emit("start", wid, f"cada {period}s ({kind})")


async def stop() -> None:
    """Cancela todos los bucles periódicos (finally del lifespan)."""
    for wid, task in list(_tasks.items()):
        task.cancel()
    _tasks.clear()
    _inflight.clear()


def scheduled() -> list[str]:
    """Ids de widgets con un bucle de background vivo (para observabilidad / tests)."""
    return [wid for wid, t in _tasks.items() if not t.done()]
