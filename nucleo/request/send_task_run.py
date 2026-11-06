"""nucleo/request/send_task_run.py — the send task's one act: the retained call crosses THE exit door, then the card's.

The executor of `nucleo/request/send_task`: no model runs here. The row is the record the exit door reads (checkpoint
1 is closed by its playbook and its end state); refused → the row ends `cannot`; asked → the row waits on the door's
question (his yes runs it again); passed → the card's own door resolves the person or asks which, queues the send, and
its echo settles the row through `circuit.settle`.
"""
from __future__ import annotations

import time
from types import SimpleNamespace

from loguru import logger

from nucleo.request import note
from nucleo.request.send_task import _question, _words_of, artefact


def _rec(uid: str, art: dict):
    """The record the exit door reads: the row is the task (checkpoint 1 is closed by its playbook and its end
    state), its words are his, nothing was read from a stranger."""
    from nucleo.circuit import ledger, spec
    row = ledger.get(uid) or {}
    e = spec.of_task(uid) or {}
    from nucleo.request.answered_task import PLAYBOOK
    return SimpleNamespace(task_id=uid, uid=uid, started=float(row.get("created_at") or time.time()), depth=0,
                           trace_id=str(row.get("trace_id") or ""), surface=str(row.get("surface") or ""),
                           sheet=str(row.get("sheet") or ""), mandate={}, reading=art.get("reading"),
                           playbook_chosen=PLAYBOOK, done_when=dict(e.get("done_when") or {}))



async def run(uid: str) -> dict:
    """The task's one act: the retained call crosses the exit door, then the card's own door. Refused → the row ends
    `cannot`; asked → the row waits (his yes runs it again); passed → the card resolves, sends, and its echo settles."""
    art = artefact(uid)
    wid, action = str(art.get("widget") or ""), str(art.get("action") or "")
    payload = dict(art.get("payload") or {})
    if not (wid and action):
        return {"ok": False, "error": "no act retained"}
    from nucleo import circuit
    from nucleo.circuit import ledger
    from nucleo.workers import exit_gate
    rec = _rec(uid, art)
    try:
        ex = exit_gate.leave(rec, "widget_data", {"widget_id": wid, "action": action, "payload": payload})
    except Exception as e:  # noqa: BLE001 — a door that could not be read sends nothing, and says so
        logger.warning(f"send_task: the exit door failed for {uid} — {e!r}")
        circuit.settle(row=uid, verdict="cannot", outcome=f"the exit door could not be read ({type(e).__name__})")
        return {"ok": False, "error": "exit door unread"}
    if ex is None:
        circuit.settle(row=uid, verdict="cannot", outcome=f"{wid}:{action} crosses no declared exit")
        return {"ok": False, "error": "no exit"}
    if ex.refused:
        circuit.settle(row=uid, verdict="cannot", outcome=ex.refused[:300])
        return {"ok": False, "error": ex.refused}
    if ex.question:
        from nucleo import consent
        ask_id = _question(uid, art, "consent", "", ex.question, consent=consent.ASK_CONSENT)
        return {"ok": False, "asked": ask_id, "row": uid}
    inner = ex.payload.get("payload") if isinstance(ex.payload, dict) and isinstance(ex.payload.get("payload"), dict) \
        else payload
    ledger.resumed(uid)
    from nucleo.flash import data_ops
    res = await data_ops.dispatch_and_report(wid, action, inner, row=uid, text=_words_of(uid))
    return res if isinstance(res, dict) else {"ok": True, "result": res}
