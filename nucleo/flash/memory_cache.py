"""nucleo/flash/memory_cache.py — bloque de MEMORIA del FlashBrain cacheado FUERA del turno (V2-011 · T114).

El problema (V2-004 → V2-011): el port a `nucleo/` metió el retriever COMPLETO de memoria en el camino caliente
del turno — `build_flash_system(recall_query=text)` disparaba `memory.query()` (embeddings HTTP a Ollama + RRF +
graph + refuerzo) SÍNCRONO en el event loop antes del LLM, cada turno. El baseline de T113 lo confirma: 112–452 ms
por turno, bloqueando el loop.

La v1 (`brains/duo/briefing.py`) NUNCA consultaba memoria por turno: pedía un briefing UNA vez al arrancar y lo
CACHEABA (TTL 300 s), inyectando el string en el prompt. Este módulo es el equivalente v2 sin Hermes: el bloque
sale de la memoria central PROPIA — de la **tabla de estado fija** (`memory.state()`, nombre/trato/ubicación/
temas/recientes: la "memoria de arranque" que neutraliza el "¿quién eres?") — y se cachea por proceso con TTL
corto + **refresco async** + **invalidación por la señal `memory.updated`** del bus. El turno lee el string
cacheado al instante; NUNCA dispara el retriever en el event loop.

El recall semántico específico (`memory.query`) NO vive aquí — es bajo demanda y fuera del loop (T115/T116).
"""
from __future__ import annotations

import asyncio
import os
import threading
import time

from loguru import logger

_TTL = float(os.getenv("NUCLEO_MEM_CACHE_TTL", "300"))   # s; corto → recall casi-vivo, pero fuera del turno
_lock = threading.Lock()
_cache = {"block": "", "op": "", "at": 0.0, "dirty": True}
_refreshing = threading.Event()   # dedup: un solo refresco en vuelo a la vez
_bus_wired = {"v": False}
# Stats de la última composición (observabilidad de memoria, V2-014 Task 2): el turno las lee para pintar
# filas MEMORY (estado/corto) en la columna de logs, con lo que se leyó y su tamaño.
_last_stats: dict = {"has_state": False, "state_fields": 0, "short_count": 0, "short_chars": 0,
                     "salient_count": 0, "has_mission": False, "op": ""}


def _set_stats(**kw) -> None:
    with _lock:
        _last_stats.update(kw)


def stats() -> dict:
    """Stats de la última lectura de memoria compuesta (para la columna de observabilidad)."""
    with _lock:
        return dict(_last_stats)


# ── composición del bloque (delega en memory.compose_state; SIEMPRE fuera del loop) ─────────────────────────
def _mission_fallback() -> str:
    """Texto de MISIÓN por defecto, del catálogo de idioma (single source de idioma). Se pasa a
    `compose_state` para no invertir la dependencia memoria→voz, y se SIEMBRA en el estado en `prime()`."""
    try:
        from voice.engine.core import langs
        return langs.current_language().mission or ""
    except Exception:
        return ""


def _compose() -> tuple[str, str]:
    """Compone el bloque de ESTADO COMPARTIDO delegando en `memory.compose_state()` (V2-027 — la memoria es la
    dueña de la composición A+B+C; este módulo solo la CACHEA off-hot-path). Devuelve (bloque, operator_name).
    Best-effort: ('', '') si la memoria no está disponible. Se ejecuta SIEMPRE en un hilo — nunca en el event loop."""
    try:
        from memory import api as memory
        block, op, stats = memory.compose_state(mission_fallback=_mission_fallback())
    except Exception:
        return "", ""
    _set_stats(**stats)
    return block, op


# ── API pública ─────────────────────────────────────────────────────────────────────────────────────────
def get() -> tuple[str, str]:
    """Lee el bloque cacheado (bloque, operator_name) AL INSTANTE — nunca bloquea el turno. Si está sucio o
    caducado, agenda un refresco async (fire-and-forget) y devuelve el valor actual (posiblemente stale, pero
    fresco por el TTL corto + la invalidación por `memory.updated`)."""
    _wire_bus()
    with _lock:
        block, op, at, dirty = _cache["block"], _cache["op"], _cache["at"], _cache["dirty"]
    if dirty or (time.time() - at) > _TTL:
        if _schedule_refresh():          # refresco SÍNCRONO (sin loop) → re-lee el valor ya fresco
            with _lock:
                block, op = _cache["block"], _cache["op"]
    return block, op


def _seed_mission() -> None:
    """SIEMBRA la MISIÓN en la memoria (state.mission) al arrancar si aún no está, tomándola del catálogo de idioma
    (`langs`, idioma del operador). Así la identidad de zaelar VIVE en la memoria — visible en el mapa y editable —
    en vez de en un prompt inglés hardcodeado (V2-027). Idempotente: si ya hay misión, no la pisa (respeta una
    misión evolucionada). Best-effort; corre en el hilo de `prime` (arranque), nunca en el turno."""
    try:
        from memory import api as memory
        cur = (memory.state().get("mission") or "").strip()
        if cur:
            return
        text = _mission_fallback()
        if text:
            memory.set_state({"mission": text})   # emite memory.updated → el refresh de prime recompone tras esto
    except Exception:
        pass


async def prime() -> None:
    """Siembra la MISIÓN (si falta) y compone el bloque UNA vez al arrancar la sesión (analogía del briefing v1),
    para que el PRIMER turno ya tenga identidad + memoria de arranque (saludo por nombre). Corre en un hilo; nunca
    rompe el arranque de la voz."""
    _wire_bus()
    await asyncio.to_thread(_seed_mission)
    await _do_refresh()


def invalidate() -> None:
    """Marca el bloque como sucio → el próximo `get()` agenda un refresco. Lo llama el sink de `memory.updated`."""
    with _lock:
        _cache["dirty"] = True


def reset() -> None:
    """Limpia el estado (tests): caché, refresco en vuelo y suscripción al bus."""
    with _lock:
        _cache.update({"block": "", "op": "", "at": 0.0, "dirty": True})
    _refreshing.clear()
    if _bus_wired["v"]:
        try:
            import bus
            bus.remove_sink(_on_bus)
        except Exception:
            pass
        _bus_wired["v"] = False


# ── mecánica interna ────────────────────────────────────────────────────────────────────────────────────
def _schedule_refresh() -> bool:
    """Agenda `_do_refresh()` en el loop en curso (fire-and-forget). Si no hay loop (tests/standalone), refresca
    en línea de forma síncrona — nunca deja el bloque vacío por no tener loop. Devuelve True SOLO si refrescó
    síncrono (para que `get()` re-lea el valor ya fresco)."""
    if _refreshing.is_set():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        _refreshing.set()
        task = loop.create_task(_do_refresh())
        task.add_done_callback(lambda t: (_refreshing.clear(), t.cancelled() or t.exception()))
        return False
    # sin loop: refresco síncrono (compose es barato: solo memory.state()).
    block, op = _compose()
    _store(block, op)
    return True


async def _do_refresh() -> None:
    """Recompone el bloque en un hilo y actualiza el caché. Best-effort."""
    try:
        block, op = await asyncio.to_thread(_compose)
        _store(block, op)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"nucleo memory-cache refresh skipped: {e}")


def _store(block: str, op: str) -> None:
    with _lock:
        # SUELO DE IDENTIDAD SAGRADO (fix del "no sabe mi nombre aunque está en el estado"): `compose_state` puede
        # FALLAR transitoriamente (lectura de la BD bajo contención en sesiones con muchas escrituras) y devolver
        # ('',''). NUNCA sobrescribimos un bloque BUENO con vacío → el nombre/trato/misión jamás desaparecen a mitad
        # de sesión por un fallo puntual. El vacío legítimo (fresh install / `reset()`) parte de un caché ya vacío,
        # así que esta guarda no lo bloquea; solo protege contra el borrado accidental del estado vivo.
        if not (block or "").strip() and (_cache["block"] or "").strip():
            _cache["dirty"] = True     # mantener el bueno, pero reintentar el refresco en el próximo get()
            return
        _cache["block"] = block
        _cache["op"] = op
        _cache["at"] = time.time()
        _cache["dirty"] = False


def _wire_bus() -> None:
    """Suscribe la invalidación a `memory.updated` con un SINK del bus (síncrono, loop-agnóstico — igual que el
    log durable). Barato: filtra el topic y marca sucio. Idempotente."""
    if _bus_wired["v"]:
        return
    try:
        import bus
        bus.add_sink(_on_bus)
        _bus_wired["v"] = True
    except Exception:
        pass


def _on_bus(rec: dict) -> None:
    if rec.get("topic") == "memory.updated":
        invalidate()
