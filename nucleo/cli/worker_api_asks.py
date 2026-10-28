"""nucleo/cli/worker_api_asks.py — the parked-ask registry: park, list, answer, purge (moved from worker_api.py).

The registry itself (`_ACTS`) stays in `worker_api`; every name of it is read as `_m.<name>` (late binding).
"""
from __future__ import annotations

import time

from nucleo import consequence as _consequence


def purge_task(task_id: str) -> int:
    """§v3·L: a dead session's PENDING requests are purged so the loop never recounts its question; answered ones
    stay (a late `hbask wait` gets a clean 404). Called by dispatch."""
    n = 0
    for corr, e in list(_m._ACTS.items()):
        if e.get("task_id") == str(task_id) and e.get("state") == "pending":
            _m._ACTS.pop(corr, None)
            n += 1
    return n


def _prune() -> None:
    """Prune old ANSWERED entries so the registry never grows without limit."""
    cut = time.time() - _m._ANSWERED_TTL_S
    for corr, e in list(_m._ACTS.items()):
        if e.get("state") == "answered" and float(e.get("created") or 0) < cut:
            _m._ACTS.pop(corr, None)


def _register_ask(rec, question: str, action: str = "ask_user", retained: dict | None = None) -> str:
    """Park a pending question (ask_user or an act's CONFIRM, §v3·K) → waiting_on=user + bus worker.ask."""
    _m._prune()
    corr = _m._new_corr(rec.task_id, action)
    _m._ACTS[corr] = {"corr_id": corr, "task_id": rec.task_id, "action": action, "question": question,
                      "state": "pending", "answer": "", "result": None, "retained": retained or {},
                      "created": time.time()}
    rec.waiting_on = "user"
    rec.ask = question
    rec.ask_corr = corr
    try:
        import bus
        bus.emit_sync("worker.ask", {"id": rec.task_id, "question": question, "corr_id": corr})
    except Exception:
        pass
    return corr


# ── ask resolution (called by FlashBrain/provider when the operator responds) ──────────────────────────────
def has_pending_ask() -> bool:
    return any(e["state"] == "pending" for e in _m._ACTS.values())


def pending_asks() -> list[dict]:
    """Pending questions, oldest first (the supervisor loop recounts them one at a time)."""
    out = [e for e in _m._ACTS.values() if e["state"] == "pending"]
    out.sort(key=lambda e: e["created"])
    return [{"corr_id": e["corr_id"], "task_id": e["task_id"], "question": e["question"],
             "action": e["action"]} for e in out]


def active_ask() -> dict | None:
    """The OLDEST pending ask (the 'active' one being recounted, §v3·M/Q5)."""
    p = _m.pending_asks()
    return p[0] if p else None


async def answer(corr_id: str, text: str) -> bool:
    """Resolve an ask: store the answer and, for an act CONFIRM answered yes, EXECUTE the retained action (§v3·K).
    Clears waiting_on. True if something was resolved."""
    e = _m._ACTS.get(corr_id)
    if not e or e["state"] != "pending":
        return False
    e["answer"] = text or ""
    e["state"] = "answered"
    retained = e.get("retained") or {}
    if retained.get("action") and _m._is_yes(text):
        try:
            from nucleo import dispatch
            rec = dispatch.get_record(e["task_id"])
            if rec is not None:
                e["result"] = await _m._exec_allow(retained["action"], retained.get("payload") or {}, rec)
        except Exception:
            pass
    _m._clear_waiting(e["task_id"], corr_id)
    return True


async def answer_active(text: str) -> bool:
    """Resolve the ACTIVE (oldest) ask — deterministic path when the operator responds by voice (§v3·M)."""
    a = _m.active_ask()
    if not a:
        return False
    return await _m.answer(a["corr_id"], text)


@_consequence.door("worker.answer", neutral=lambda *_a, **_k: _m.has_pending_ask())
def answer_active_soon(text: str) -> bool:
    """Fire-and-forget onto the server loop (§v3·D/O), called from the FlashBrain's job thread. True if there WAS
    an ask to answer (so voice can confirm)."""
    if not _m.has_pending_ask():
        return False
    try:
        import asyncio

        from nucleo import dispatch
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_m.answer_active(text), loop)
        else:
            asyncio.ensure_future(_m.answer_active(text))
        return True
    except Exception:
        return False


def _clear_waiting(task_id: str, corr_id: str) -> None:
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(task_id)
        if rec is not None and getattr(rec, "ask_corr", "") == corr_id:
            rec.waiting_on = ""
            rec.ask = ""
            rec.ask_corr = ""
    except Exception:
        pass


def _is_yes(text: str) -> bool:
    t = (text or "").strip().lower()
    return any(w in t for w in ("sí", "si", "vale", "adelante", "hazlo", "ok", "yes", "dale", "confirmo"))


from nucleo.cli import worker_api as _m  # noqa: E402 — last, so importing this module first still resolves
