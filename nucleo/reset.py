"""nucleo/reset.py — operator HARD RESET (the frontend's «Reset» button).

CAREFUL sequence requested by the operator (2026-07-10), in this exact ORDER:

  1. FREEZE the "live state containers" — the work CURRENTLY IN PROGRESS: browser tasks (searches), escalations
     to SlowBrain, widget generation/editing — in a snapshot → **STATE** memory (`memory.set_state`, neither short
     nor long: it is the state of what was being done).
  2. Leave a RECORD of the stop ORDER → **SHORT-TERM** memory ("at this moment we stop everything…").
  3. KILL those background processes.

It reinvents nothing: it reuses the primitives that ALREADY exist (browser `tasks.active_ids/get/cancel`,
`escalate.pending/reset`, `brain_notes.drain`, `memory.set_state/write`). Everything is best-effort: a failure in
one piece never aborts the rest or breaks voice operation. It runs IN THE server PROCESS (operating on in-process
state), triggered by `POST /reset/hard`. The endpoint adds canvas closing and session cleanup (emits widget close +
session RESET); only the PROCESSES + MEMORY portion belongs here.
"""
from __future__ import annotations

import time

from loguru import logger


# ── (1) FREEZE: snapshots of live work (best-effort, read-only) ─────────────────────────────────────────────
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
        jobs = generator._jobs_read()   # read-only peek at the in-flight generation journal
        return [{"widget": wid, "kind": (j or {}).get("kind")} for wid, j in (jobs or {}).items()]
    except Exception:
        return []


def abandon_work(*, source: str = "reset") -> dict:
    """KILL all background work and CLEAR the markers saying «we are doing X» — the core shared by the Reset
    button and the VOICE command («Zaelar, para todo lo que estamos haciendo y quédate tranquilo»).

    Operator decision (2026-08-31, live, superseding the «freeze to resume» sequence from 2026-07-10): stopping
    means DISCARDING. After its reset, the new session's greeting said «sigo con lo del digestólogo» with not a
    single worker alive — the state contained `trabajo_interrumpido` with the frozen escalation, durable `task.*`
    slots remained, and the short-term record said the work «queda CONGELADO», which the model reads as an
    invitation to resume it. In the operator's words: «si en la memoria de corto plazo o en el estado estaba
    marcado que estábamos haciendo una tarea, eso también se tiene que limpiar».

    What dies here: browser, Brain Workers, pending escalations, queued [SYSTEM] notes, the `activity`/`sessions`
    projections, `trabajo_interrumpido` (ALWAYS set to `{}` — details of what was killed travel in the RETURN,
    for the observability event, not in memory), and `task.*` slots. What is NOT touched: profile, facts, ingested
    messages, the agenda — this discards WORK, not memories. The short-term record is an INSTRUCTION (V2-214
    doctrine): it says that nothing is pending and nothing should be resumed."""
    ts = time.strftime("%Y-%m-%d %H:%M")
    nav = _snapshot_navegador()
    esc = _snapshot_escalations()
    jobs = _snapshot_widget_jobs()
    frozen_n = len(nav) + len(esc) + len(jobs)

    killed = {"navegador": 0, "escaladas": 0, "workers": 0, "notas": 0, "ledger": 0, "widgets_en_blanco": 0,
              "task_slots": 0}
    try:
        from widgets.navegador import tasks as nt
        for tid in list(nt.active_ids()):
            nt.cancel(tid)
            killed["navegador"] += 1
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: cancelar navegador falló: {e}")
    # V2-038: REALLY KILL live Brain Workers (group kill via the backend), rather than merely clearing the registry.
    try:
        from nucleo import dispatch
        killed["workers"] = dispatch.cancel_all(reason=source)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: cancel_all workers falló: {e}")
    try:
        from nucleo.flash import escalate
        killed["escaladas"] = len(escalate.pending())
        escalate.reset()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: reset escaladas falló: {e}")
    # V2-042: clear RAIL RUNS (unresolved, ringing searches…) — session state, not durable.
    try:
        from nucleo import rails
        rails.clear_all()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: clear rails falló: {e}")
    try:
        from voice import brain_notes
        killed["notas"] = len(brain_notes.drain())   # discard pending [SYSTEM] notes → they do not re-trigger work
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: drenar brain_notes falló: {e}")
    # THE MARKERS: state and memory stop saying that work is in progress. See the docstring.
    try:
        from memory import api as memory
        memory.set_state({"trabajo_interrumpido": {}, "activity": [], "sessions": []})
        killed["task_slots"] = memory.clear_slot_prefix("task.")
        resumen = f"navegador {len(nav)} · escaladas {len(esc)} · widgets {len(jobs)}"
        memory.write(
            f"[PARADO] El operador mandó parar y DESCARTAR todo el trabajo en curso ({resumen}, {ts}, vía "
            f"{source}). No queda NADA pendiente de reanudar: no retomes, no continúes y no digas que sigues "
            f"con ninguna de esas tareas — solo existen de nuevo si el operador las vuelve a pedir.",
            level="short", kind="event", importance=0.6,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"abandon_work: limpiar las marcas falló: {e}")
    logger.info(f"abandon_work({source}): matados {killed} · descartados {frozen_n} en curso")
    return {"frozen": frozen_n, "killed": killed, "when": ts, "source": source,
            "discarded": {"navegador": nav, "escaladas": esc, "widgets_en_curso": jobs}}


def abandon_work_soon(*, source: str) -> None:
    """Fire-and-forget `abandon_work` for HOT paths — the voice's `stop_worker('todo')` («Zaelar, para todo lo
    que estamos haciendo y quédate tranquilo», operator 2026-08-31). Killing workers is not enough: the markers
    saying «we are doing X» (`trabajo_interrumpido`, `task.*` slots, escalations, queued notes) still said the
    opposite and the next greeting resumed the dead task. Same core as the Reset button, MINUS resetting: it does
    not close the session, delete the chat, or clear the process history (what was just cancelled must be VISIBLE
    there as `cancelled`). In a separate thread because it writes SQL and kills processes; without a loop (tests,
    synchronous calls), it runs directly."""
    try:
        from voice.observer import emit
        emit("brain", "🧹 trabajo DESCARTADO (marcas incluidas)", text=f"para todo → abandon_work ({source})",
             role="system")
    except Exception:
        pass
    import asyncio
    try:
        asyncio.get_running_loop().create_task(asyncio.to_thread(abandon_work, source=source))
    except RuntimeError:
        abandon_work(source=source)


def reset_all() -> dict:
    """The complete HARD RESET («Reset» button): `abandon_work` + what only makes sense when resetting — clear the
    process history, forget the rehydration trail, blank the widgets, clear UI state, and DELETE the conversation
    buffer (the chat is deleted, including the window SEEDING: without this, the new session's first greeting
    re-imported the deleted conversation and said «sigo con ello» — observed 2026-08-31)."""
    out = abandon_work(source="reset")
    frozen_n, killed, ts = out["frozen"], out["killed"], out["when"]
    blanked = {}
    # V2-084: clear the Process HISTORY (worker ledger) → processes are LEFT BLANK after reset
    # («empezamos de cero»). ONLY reset: the VOICE command «para todo» deliberately preserves the history — what
    # it just cancelled must be VISIBLE there as `cancelled`, which differs from starting from zero.
    try:
        from nucleo.workers import ledger as _ledger
        killed["ledger"] = _ledger.clear()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: clear ledger falló: {e}")
    # REHYDRATION (2026-08-12): delete the trail of live sessions and web continuity. Without this, the operator
    # presses Reset «para empezar de cero», kills the work manually… and the next startup RESURRECTS it because
    # the trail said it was in flight. A reset is an order, not a crash.
    try:
        from nucleo import dispatch as _dispatch
        from nucleo import rehydrate as _rehydrate
        _rehydrate.forget()
        _dispatch._WEB_RESUME.clear()
        _dispatch._resume_persist()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: limpiar rastro de rehidratación falló: {e}")
    # (3b) BLANK SURFACES (2026-08-12, operator request). Closing cards did not clear their DATA: after a reset,
    # the operator requested a new search and the results sheet displayed the previous one IN FULL while the new
    # worker was still working. A widget showing earlier work as current is just as misleading as a fallen agent
    # painted blue. Preserve credentials/profiles and respect the widget that declares its data to be the operator's
    # RECORD (the agenda) — details in `widgets/reset.py`.
    try:
        from widgets import reset as _wreset
        blanked = _wreset.blank_all()
        killed["widgets_en_blanco"] = len(blanked.get("blanked") or [])
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: dejar los widgets en blanco falló: {e}")
    # THE CONVERSATION BUFFER (2026-08-31): «el chat se borra» includes seeding. `recent_window` reads the short-term
    # conversation cards and the provider seeds its window with them after reconnecting — a reset that does not
    # invalidate them lets the deleted conversation enter through the back door.
    try:
        from memory import api as memory
        killed["conversacion"] = memory.clear_conversation()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: borrar el buffer conversacional falló: {e}")
    # (3c) …and the STATE that DEPENDS on all of that. `activity`/`sessions` were already emptied above, but the
    # rest continued describing a world we had just dismantled: open widgets that no longer exist, the MRU of «those
    # you used a moment ago» pointing to the previous test, and live rail runs from a dead task. The brain read that
    # on every prompt, so it started the new test believing it was still in the old one.
    try:
        from memory import api as memory
        memory.set_state({"open_widgets": [], "recent_widgets": [], "rails": []})
        memory.kv_del("canvas_layout")     # the layout saved on the server also back to zero (rehydration)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"reset_all: limpiar el estado de UI falló: {e}")

    logger.info(f"HARD RESET: descartados {frozen_n} · matados {killed}")
    # `widgets` travels in the response so it is possible to SEE what was emptied and what was preserved: showing
    # the list of preserved items prevents the «¿y mi agenda?» surprise. `discarded` (from abandon_work) carries
    # WHAT was killed to the RESET observability event — memory no longer stores it, but the session file does.
    return {"frozen": frozen_n, "killed": killed, "when": ts, "widgets": blanked,
            "discarded": out.get("discarded")}
