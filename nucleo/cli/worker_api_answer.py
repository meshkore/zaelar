"""nucleo/cli/worker_api_answer.py — his answer to a task's DURABLE question (V2-851 §3/§3a), moved by concern out of
`worker_api_asks` (which records the question). The answer is recorded on the question's artefact, a retained act runs
only on his yes (the confirmation recogniser of `widgets.confirm`, never a substring list), the row stops waiting and
the session that asked is resumed by id (`worker_api_resume`). Every name of the registry is read as `_m.<name>`.
"""
from __future__ import annotations

import time

from nucleo import consequence as _consequence
from nucleo.cli.worker_api_asks import _artefact, _keep, _note, open_ask, open_asks


def _says_yes(question: str, text: str) -> bool:
    """His yes to a retained act, read by the confirmation recogniser (`widgets.confirm`): a plain yes, or the judge's
    YES; a «no» anywhere that is the last word said («así no») is no."""
    from widgets import confirm as _wc
    v = _wc.classify_reply(text)
    if v == "no":
        return False
    if v == "yes" and _wc.is_plain_answer(text, v):
        return True
    judged = _wc._judge(str(question or ""), str(text or ""))
    return v == "yes" if judged is None else judged == "yes"


def _record_for(entry: dict):
    """The live record of the asking session, or a stand-in built from its row (the process ended after asking)."""
    try:
        from nucleo import dispatch
        rec = dispatch.get_record(entry.get("task_id"))
        if rec is not None:
            return rec
    except Exception as e:  # noqa: BLE001
        _note(e)
    from types import SimpleNamespace
    row = {}
    try:
        from nucleo.circuit import ledger
        _ts = ledger.store()
        row = _ts.task_get(entry.get("uid") or "") or {}
    except Exception as e:  # noqa: BLE001
        _note(e)
    return SimpleNamespace(task_id=str(entry.get("task_id") or ""), uid=str(entry.get("uid") or ""),
                           trace_id=str(row.get("trace_id") or ""), surface=str(row.get("surface") or ""),
                           sheet=str(row.get("sheet") or ""), started=float(row.get("started_at") or 0),
                           depth=0, parent_task_id="", kind=str(row.get("kind") or "generic"), goal=str(row.get("goal") or ""))


async def answer(corr_id: str, text: str, *, resume: bool = True, choice: int | None = None) -> bool:
    """Resolve the question `corr_id` with his `text`: the artefact records the answer, a retained act runs only on his
    yes (`_says_yes`), the row stops waiting and — when the asking session already ended — that session is resumed by
    id with the answer. An INLINE row's question (`nucleo/request/inline_ask`) re-runs its retained act instead, with
    the answer — or the candidate the binding verdict chose (`choice`) — bound. True if an open question was resolved."""
    e = _m._ACTS.get(corr_id)
    uid = str((e or {}).get("uid") or "")
    if e is None:
        a = next((a for a in open_asks() if a["ask_id"] == corr_id), None)
        if a is None:
            return False
        uid = a["task_id"]
        e = dict(_artefact(uid)) or {"corr_id": corr_id, "ask_id": corr_id, "uid": uid, "question": a["question"],
                                     "retained": {}, "task_id": ""}
        e.setdefault("uid", uid)
    if e.get("state") not in (None, "pending"):
        return False
    e["answer"] = text or ""
    e["state"] = "answered"
    e["answered_at"] = time.time()
    retained = e.get("retained") or {}
    if e.get("inline"):
        _keep(uid, e)
        try:
            from nucleo.request import inline_ask
            e["result"] = await inline_ask.rerun(uid, e, text, choice)
        except Exception as ex:  # noqa: BLE001
            _note(ex)
        return True
    if retained.get("action") and _says_yes(str(e.get("question") or ""), text):
        from nucleo.workers import taint as _taint
        rec = _record_for(e)
        _taint.cleared(rec)        # his yes: what the session read before is behind his confirmation (§4a)
        try:
            with _taint.during(rec, source=str(retained["action"])):
                e["result"] = await _m._exec_allow(retained["action"], retained.get("payload") or {}, rec)
            from nucleo.workers import task_files      # his yes ran it: its artefact on the task, at the door
            task_files.record(rec, str(retained["action"]), retained.get("payload") or {}, e["result"])
            task_files.said(rec, str(retained["action"]), retained.get("payload") or {}, e["result"])
        except Exception as ex:  # noqa: BLE001 — `as e` here unbound the entry itself (Python deletes the name)
            _note(ex)
    if corr_id in _m._ACTS:
        _m._ACTS[corr_id] = e
    _keep(uid, e)
    if uid:                                    # `ledger.resumed` owns the row's end of the wait (V2-851 F1a)
        from nucleo.circuit import ledger
        ledger.resumed(uid)
    _m._clear_waiting(str(e.get("task_id") or ""), corr_id)
    if resume and uid:
        try:
            from nucleo.cli import worker_api_resume as _res
            _res.resume_soon(uid, e)
        except Exception as ex:  # noqa: BLE001
            _note(ex)
    return True


async def answer_task(uid: str, ask_id: str, text: str) -> bool:
    """The screen's answer: it names its task and its question. False (→ 409) when that question is not open. A
    screen option IS a declared candidate: picking it is its index, never a reading of words."""
    a = open_ask(uid)
    if a is None or a["ask_id"] != str(ask_id or ""):
        return False
    opts = [str(o) for o in (_artefact(uid).get("options") or [])]
    choice = opts.index(str(text)) if str(text) in opts else None
    return await _m.answer(a["ask_id"], text, choice=choice)


@_consequence.door("worker.answer", neutral=False)
def answer_soon(ask_id: str, text: str, choice: int | None = None) -> bool:
    """Fire-and-forget onto the server loop, from the FlashBrain's job thread: answer the question the turn's verdict
    BOUND (`worker_api_bind`). True if the question was open."""
    if not any(a["ask_id"] == ask_id for a in open_asks()) and not (
            (_m._ACTS.get(ask_id) or {}).get("state") == "pending"):
        return False
    try:
        import asyncio

        from nucleo import dispatch
        loop = getattr(dispatch, "_LOOP", None)
        if loop is not None:
            asyncio.run_coroutine_threadsafe(_m.answer(ask_id, text, choice=choice), loop)
        else:
            asyncio.ensure_future(_m.answer(ask_id, text, choice=choice))
        return True
    except Exception as e:  # noqa: BLE001
        _note(e)
        return False


from nucleo.cli import worker_api as _m  # noqa: E402 — last, so importing this module first still resolves
