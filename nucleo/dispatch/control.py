"""What the turn does to a running errand: inject a refinement, cancel, pause, resume, stop all.
Every package name is read through `_d`, so a patch of `dispatch.<name>` reaches the code here."""
from __future__ import annotations

import asyncio

from loguru import logger

from nucleo import dispatch as _d


def _schedule_auto_resume(req: str) -> None:
    """V2-049: automatically resumes an incomplete web operation after a brief pause (without an operator nudge).
    Emits another escalation for the SAME request; the listener matches it to the newly recorded `_WEB_RESUME` entry
    and CONTINUES (same tab + `--resume`). The `_WEB_RESUME[count]` cap stops it if something is genuinely broken."""
    async def _later() -> None:
        try:
            await asyncio.sleep(5.0)
            from nucleo.acts import errand as escalate
            escalate.escalate_to_slowbrain(req, context={"kind": "web", "auto_resume": True})
            logger.info(f"dispatch: AUTO-RESUME de gestión web incompleta: {req[:80]}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: auto-resume falló: {e}")
    try:
        asyncio.create_task(_later())
    except Exception:
        pass


# ── inyeccion (↓) ────────────────────────────────────────────────────────────────────────────────────────
async def inject(which: str, message: str) -> list[str]:
    """Inject `message` into the session(s) `which` resolves to; returns the injected tids (V2-029, §v3·G)."""
    tids = _d.resolve_sessions(which)
    done = []
    for tid in tids:
        r = _d._SESSIONS.get(tid)
        if not r:
            continue
        try:
            if r.session:
                await r.session.inject(message)
            else:
                # still QUEUED (no process): pending on the record, piggybacked on the worker's first contact (§v3·H)
                from nucleo.workers.session import Inject
                r.injects.append(Inject(text=message, ts=_d.time.time()))
            done.append(tid)
            _d._sheets.recheck_rows(getattr(r, "sheet", ""), message, relayed=True)   # V2-782 T3.3: our words, not his
        except Exception as e:  # noqa: BLE001
            logger.warning(f"dispatch: inject a {tid} falló: {e}")
    return done


def take_pending_injects(tid) -> list[str]:
    """Piggyback: worker_api the calls al responder a a bridge → entrega the inyecciones pending (§v3·H).
    Lee the RECORD (no the session): also entrega it inyectado mientras the task esperaba in the cola of the pool."""
    r = _d._SESSIONS.get(str(tid))
    if not r:
        return []
    out = []
    for inj in r.injects:
        if inj.state == "pending":
            inj.state = "delivered"
            out.append(inj.text)
    return out


# ── MATAR (with cortesia) ─────────────────────────────────────────────────────────────────────────────────
def cancel_session(tid, *, reason: str = "operator") -> bool:
    """Mata a session: cancela su asyncio.Task (→ the backend mata the grupo of procesos) and purge record +
    chip + state of inmediato (reflejo instantaneo). Idempotente."""
    key = str(tid)
    r = _d._SESSIONS.get(key)
    if not r:
        return False
    if r.session:
        try:
            asyncio.ensure_future(r.session.stop(reason=reason))
        except Exception:
            pass
    if r.task and not r.task.done():
        try:
            r.task.cancel()
        except Exception:
            pass
    _d._SESSIONS.pop(key, None)
    try:
        from nucleo import worker_api
        worker_api.purge_task(key)   # §v3·L: el loop no debe relatar la pregunta de un muerto
    except Exception:
        pass
    try:
        from voice.observer import emit
        _tx = {"trace": r.trace_id, "span": f"worker:{key}"} if r.trace_id else {}   # V2-044
        emit("task", "cancel", text=(r.label or r.goal or "")[:120], role="system",
             extra={"id": key, "goal": (r.goal or "")[:120], **_tx})
        emit("task", "end", extra={"id": key, "ok": False, **_tx})
    except Exception:
        pass
    _d.sync_state()
    return True


def cancel_all(*, reason: str = "reset") -> int:
    n = 0
    for k in list(_d._SESSIONS.keys()):
        if _d.cancel_session(k, reason=reason):
            n += 1
    return n


# ── V2-065 (2026-07-23): PAUSE ≠ kill — the operator's ⏻. Unlike `cancel_all` (irreversible, Reset), this freezes
# live workers (SIGSTOP, `workers/base.py::pause`); `resume_all()` continues them. A backend that cannot pause
# returns False and nothing breaks. Best-effort, synchronous.
def pause_all() -> int:
    n = 0
    for r in _d._SESSIONS.values():
        if r.status not in _d.LIVE_SESSION_STATES or not r.session:
            continue
        try:
            if r.session.pause():
                n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"pause_all: worker {r.task_id} falló al pausar: {e}")
    if n:
        _d.sync_state()
    return n


def resume_all() -> int:
    n = 0
    for r in _d._SESSIONS.values():
        if not r.paused or not r.session:
            continue
        try:
            if r.session.resume():
                n += 1
        except Exception as e:  # noqa: BLE001
            logger.warning(f"resume_all: worker {r.task_id} falló al reanudar: {e}")
    if n:
        _d.sync_state()
    return n


async def stop_all_async(*, grace: float = 2.0) -> int:
    """Apagado ORDENADO of the lifespan (§v3·L): for the backends waiting su cierre (killpg) ANTES of tumbar the
    loop. Devuelve how many sessions habia."""
    recs = list(_d._SESSIONS.values())
    for r in recs:
        if r.session:
            try:
                await r.session.stop(grace=grace, reason="shutdown")
            except Exception:
                pass
        if r.task and not r.task.done():
            r.task.cancel()
    n = len(recs)
    _d._SESSIONS.clear()
    return n
