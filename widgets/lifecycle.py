"""widgets/lifecycle.py — CICLO DE VIDA de un widget + su integración con la MEMORIA (V2-017).

Un widget nace (CREATE), cambia (MODIFY) y muere (DELETE). Cada transición tiene que dejar rastro en la
**memoria central** (`memory/`) — no para que el widget "exista" en memoria (el catálogo vivo es la fuente de
verdad de qué hay en el canvas), sino para que zaelar tenga MEMORIA HUMANA de lo que hizo: si mañana el operador
pregunta "¿dónde está el widget de aquel que teníamos?", zaelar debe poder decir "lo mandaste borrar el <fecha>".

Reglas (ver `zaelar-memory.md §Acciones ↔ memoria`):
  - **Nunca se borra el histórico.** Borrar un widget elimina su CÓDIGO y sus DATOS del disco, pero escribe un
    evento de memoria («borrado el <fecha> a petición del operador»). El recuerdo de su creación se conserva —
    tener ambos (creado el X, borrado el Y) ES la historia. El retriever los sirve; el catálogo vivo ya NO lo
    lista, así que zaelar no alucina que sigue ahí.
  - **La memoria la escriben los widgets por la fachada** (`memory.write`, cola async loop-agnóstica) — los
    widgets durables son escritores sancionados de la memoria (ver CLAUDE.md).

BORRAR es DETERMINISTA (rm de carpeta + `store.delete` + invalidar catálogo + cerrar la tarjeta): NO necesita el
agente de código headless (eso es solo para CREAR/MODIFICAR, que escriben código). Por eso lo puede disparar el
FlashBrain al instante (tras confirmación — ver `widgets/confirm.py`), en el loop que resuelva la confirmación
(job-thread de voz o loop del server): `delete_widget` es una corrutina que corre el I/O de disco en un hilo.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time

from loguru import logger

from . import runtime, store

HERE = os.path.dirname(os.path.abspath(__file__))


def _emit_widget(action: str, wid: str, src: str = "system") -> None:
    """Evento de canvas (observer → SSE /events): el frontend cierra/actualiza la tarjeta. Best-effort.
    V2-039: `src` = quién ordenó el borrado (flash / user / worker / system)."""
    try:
        from voice.observer import emit
        emit("widget", action, extra={"id": wid, "src": src})
    except Exception:
        pass


def _mem_write(text: str, importance: float) -> None:
    """Escribe un evento de ciclo de vida en la memoria central. `memory.write` encola de forma loop-agnóstica
    (call_soon_threadsafe), así que es seguro llamarlo desde el job-thread de voz o el loop del server."""
    try:
        from memory import api as memory
        memory.write(text, kind="event", level="mid", importance=importance)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widget lifecycle: memory write skipped: {e}")


def record_created(widget_id: str, spec: str = "") -> None:
    """Da de ALTA en memoria un widget recién creado (evento recallable, con id + qué muestra + fecha). Lo llama
    el agente de código del SlowBrain tras generar el widget. Best-effort."""
    wid = (widget_id or "").strip().lower()
    if not wid:
        return
    meta = runtime.get(wid) or {}
    title = meta.get("title") or wid
    what = (meta.get("whenToUse") or "").strip() or (spec or "").strip()[:100]
    when = time.strftime("%Y-%m-%d")
    tail = f" para: {what}." if what else "."
    _mem_write(f"[widget:{wid}] El widget «{title}» fue CREADO el {when}{tail}", importance=0.5)


async def delete_widget(widget_id: str, src: str = "system") -> dict:
    """BORRA un widget para siempre: quita su carpeta (`widgets/<id>/`) y su store privado (`_data/<id>/`),
    invalida el catálogo, cierra su tarjeta en el canvas y escribe la LÁPIDA en memoria (histórico conservado).
    Determinista, sin agente headless. Corre el I/O de disco en un hilo. Nunca lanza.
    V2-039: `src` = quién ordenó el borrado (para la auditoría del canvas)."""
    wid = (widget_id or "").strip().lower()
    if not wid:
        return {"ok": False, "error": "id vacío"}
    meta = runtime.get(wid) or {}
    folder = os.path.join(HERE, wid)
    if not meta and not os.path.isdir(folder):
        return {"ok": False, "error": "widget no encontrado"}
    title = meta.get("title") or wid
    what = (meta.get("whenToUse") or "").strip()

    def _rm() -> None:
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"widget lifecycle: rmtree {folder} falló: {e}")
        try:
            store.delete(wid)          # su store privado muere con él (state.json + media)
        except Exception:
            pass

    await asyncio.to_thread(_rm)
    runtime.invalidate()               # el catálogo/identify dejan de conocerlo YA (el cerebro no lo mostrará)
    _emit_widget("delete", wid, src)   # cierra la tarjeta abierta en el canvas (con procedencia)

    # LÁPIDA en memoria: NO borramos el histórico. Evento recallable → "lo mandaste borrar el <fecha>".
    when = time.strftime("%Y-%m-%d")
    desc = f" ({what})" if what else ""
    _mem_write(
        f"[widget:{wid}] El widget «{title}»{desc} fue BORRADO el {when} a petición del operador. Ya no existe "
        f"en el canvas; si el operador pregunta por él, recuérdale que lo mandó borrar.",
        importance=0.55,
    )
    logger.info(f"widget lifecycle: BORRADO '{wid}' (carpeta+store+lápida en memoria)")
    return {"ok": True, "id": wid, "title": title}
