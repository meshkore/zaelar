"""nucleo/reset.py — HARD RESET del operador (el botón «Reset» del frontend).

Secuencia CAUTELOSA pedida por el operador (2026-07-10), en este ORDEN exacto:

  1. CONGELAR los "contenedores de estado vivo" — el trabajo EN CURSO ahora mismo: tareas del navegador
     (búsquedas), escaladas al SlowBrain, generación/edición de widgets — en un snapshot → memoria de **ESTADO**
     (`memory.set_state`, no corto ni largo: es el estado de qué se estaba haciendo).
  2. Dejar un REGISTRO de la ORDEN de parada → memoria de **CORTO plazo** ("en este momento detenemos todo…").
  3. MATAR esos procesos de fondo.

No reinventa nada: reutiliza las primitivas que YA existen (navegador `tasks.active_ids/get/cancel`,
`escalate.pending/reset`, `brain_notes.drain`, `memory.set_state/write`). Todo best-effort: un fallo en una pieza
nunca aborta el resto ni rompe la voz. Corre EN EL PROCESO del server (opera sobre estado in-process), disparado
por `POST /reset/hard`. El cierre del canvas y la limpieza de sesión los añade el endpoint (emite widget close +
session RESET); aquí solo va la parte de PROCESOS + MEMORIA.
"""
from __future__ import annotations

import time

from loguru import logger


# ── (1) CONGELAR: snapshots del trabajo vivo (best-effort, read-only) ───────────────────────────────────────
def _snapshot_navegador() -> list[dict]:
    try:
        from widgets.navegador import tasks as nt
        out = []
        for tid in nt.active_ids():
            t = nt.get(tid) or {}
            out.append({"id": tid, "goal": (t.get("goal") or "")[:160],
                        "status": t.get("status"), "phase": t.get("phase")})
        return out
    except Exception:
        return []


def _snapshot_escalations() -> list[dict]:
    try:
        from nucleo.flash import escalate
        return [{"request": (p.get("request") or "")[:160]} for p in escalate.pending()]
    except Exception:
        return []


def _snapshot_widget_jobs() -> list[dict]:
    try:
        from widgets import generator
        jobs = generator._jobs_read()   # read-only peek al diario de generación en vuelo
        return [{"widget": wid, "kind": (j or {}).get("kind")} for wid, j in (jobs or {}).items()]
    except Exception:
        return []


def reset_all() -> dict:
    """Ejecuta la secuencia congelar → registrar → matar. Devuelve un resumen para la UI/logs."""
    ts = time.strftime("%Y-%m-%d %H:%M")
    nav = _snapshot_navegador()
    esc = _snapshot_escalations()
    jobs = _snapshot_widget_jobs()
    frozen_n = len(nav) + len(esc) + len(jobs)

    # (1) + (2): congelar en ESTADO y registrar la orden en CORTO. La memoria ordena las inserciones (cola async).
    try:
        from memory import api as memory
        if frozen_n:
            memory.set_state({"trabajo_interrumpido": {
                "cuando": ts, "navegador": nav, "escaladas": esc, "widgets_en_curso": jobs,
            }})
        resumen = f"navegador {len(nav)} · escaladas {len(esc)} · widgets {len(jobs)}"
        memory.write(
            f"[RESET] El operador detuvo TODO el trabajo en curso ({resumen}). "
            f"El estado de lo que se estaba haciendo queda CONGELADO en la memoria de estado ({ts}).",
            level="short", kind="event", importance=0.6,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: memoria (congelar/registro) falló: {e}")

    # (3) MATAR los procesos de fondo (tras congelar y registrar).
    killed = {"navegador": 0, "escaladas": 0, "workers": 0, "notas": 0, "ledger": 0}
    try:
        from widgets.navegador import tasks as nt
        for tid in list(nt.active_ids()):
            nt.cancel(tid)
            killed["navegador"] += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: cancelar navegador falló: {e}")
    # V2-038: MATAR DE VERDAD los Brain Workers vivos (kill de grupo vía el backend), no solo limpiar el registro.
    try:
        from nucleo import dispatch
        killed["workers"] = dispatch.cancel_all(reason="reset")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: cancel_all workers falló: {e}")
    # V2-084: vaciar el HISTÓRICO de Procesos (worker ledger) → los procesos quedan EN BLANCO tras el reset
    # («empezamos de cero»). No toca estado/memoria/datos de widgets: es solo el registro de procesos.
    try:
        from nucleo.workers import ledger as _ledger
        killed["ledger"] = _ledger.clear()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: clear ledger falló: {e}")
    try:
        from nucleo.flash import escalate
        killed["escaladas"] = len(escalate.pending())
        escalate.reset()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: reset escaladas falló: {e}")
    # V2-042: limpiar los RUNS de los RAILS (búsquedas sin_resolver, sonando…) — estado de sesión, no durable.
    try:
        from nucleo import rails
        rails.clear_all()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: clear rails falló: {e}")
    try:
        from voice import brain_notes
        killed["notas"] = len(brain_notes.drain())   # descarta notas [SISTEMA] pendientes → no re-disparan trabajo
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: drenar brain_notes falló: {e}")

    logger.info(f"HARD RESET: congelados {frozen_n} · matados {killed}")
    return {"frozen": frozen_n, "killed": killed, "when": ts}
