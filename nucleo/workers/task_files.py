"""nucleo/workers/task_files.py — what a worker produces is recorded on ITS task when produced, at the door (V2-851 F2,
§3 P1-2).

«Todo siempre está ahí disponible»: the session is a cache, the row and its artefacts are the truth. A mechanism,
not a prompt rule: the worker door (`worker_api.worker_act`, and the retained act his yes runs) calls `record` after
every act, so no act through the bridge leaves no trace on the task (`task_artifacts` slot `acts`, bounded). The
worker's own files ride the same table (`file:<name>` slots, bridge acts `file_put` / `files`), and `verify` asks the
circuit's verifier (`circuit/verify`) against the end state the task declared — it never closes: `circuit.settle`
closes.

Reached only through the ledger (`nucleo.circuit.ledger`), the task store's one importer.
"""
from __future__ import annotations

import time

from loguru import logger

ACTS_SLOT = "acts"
FILE_PREFIX = "file:"
#: How many act records a task keeps (the newest win): a looping worker cannot grow its row without bound.
ACTS_KEPT = 200
#: The largest text a worker file may hold in its slot.
FILE_CHARS = 200_000
_REF_KEYS = ("ref", "id", "child_id", "errand", "widget", "cuando")


def _uid(rec) -> str:
    return str(getattr(rec, "uid", "") or "")


def _store():
    from nucleo.circuit import ledger
    return ledger.store()


def _summary(action: str, payload: dict, res) -> dict:
    p = payload if isinstance(payload, dict) else {}
    out = {"at": time.time(), "act": action, "ok": bool(isinstance(res, dict) and res.get("ok"))}
    for k in ("tool", "widget_id", "action", "agent", "name"):
        if p.get(k):
            out[k] = str(p[k])[:80]
    r = res.get("result") if isinstance(res, dict) and isinstance(res.get("result"), dict) else {}
    ref = next((r[k] for k in _REF_KEYS if r.get(k)), "")
    if ref:
        out["ref"] = str(ref)[:160]
    if isinstance(res, dict) and res.get("error"):
        out["error"] = str(res["error"])[:200]
    if isinstance(res, dict) and res.get("status") == "pending":
        out["asked"] = str(res.get("corr_id") or "")
    return out


def record(rec, action: str, payload: dict, res) -> None:
    """The act's artefact on its task. Never raises: the act already happened."""
    uid = _uid(rec)
    if not uid:
        return
    try:
        ts = _store()
        got = ts.artifact_get(uid, ACTS_SLOT)
        rows = list(got) if isinstance(got, list) else []
        rows.append(_summary(action, payload, res))
        ts.artifact_put(uid, ACTS_SLOT, rows[-ACTS_KEPT:])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"task_files: act not recorded on {uid} ({e!r})")


def put(rec, payload: dict) -> dict:
    """Bridge act `file_put {name, text}`: a file of THIS task, in its own slot."""
    uid = _uid(rec)
    name = str((payload or {}).get("name") or "").strip().replace("/", "_")[:80]
    text = (payload or {}).get("text")
    if not uid:
        return {"ok": False, "error": "this session has no task row to keep a file on"}
    if not name or not isinstance(text, str):
        return {"ok": False, "error": "file_put needs `name` and `text` (the file's content as text)"}
    if len(text) > FILE_CHARS:
        return {"ok": False, "error": f"the file is {len(text)} chars; a task file holds at most {FILE_CHARS}"}
    try:
        _store().artifact_put(uid, FILE_PREFIX + name, {"name": name, "text": text, "at": time.time()})
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"the file was not kept: {type(e).__name__}"}
    return {"ok": True, "result": {"ref": f"task:{uid}/{name}", "chars": len(text)}}


def listing(rec) -> dict:
    """Bridge act `files`: the files this task holds and how many acts it recorded."""
    uid = _uid(rec)
    if not uid:
        return {"ok": True, "result": {"files": [], "acts": 0}}
    try:
        from nucleo.circuit import ledger
        arts = ledger.artifacts(uid) or {}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"the task's files are unreadable: {type(e).__name__}"}
    files = [{"name": str(k)[len(FILE_PREFIX):], "chars": len(str((v or {}).get("text") or ""))}
             for k, v in arts.items() if str(k).startswith(FILE_PREFIX)]
    acts = arts.get(ACTS_SLOT)
    return {"ok": True, "result": {"files": files, "acts": len(acts) if isinstance(acts, list) else 0}}


def verify(rec) -> dict:
    """Bridge act `verify`: the circuit's verdict on the end state the task declared — the worker asks, never closes.
    `met` True / False / None (None = could not be read, never a failure)."""
    uid = _uid(rec) or str(getattr(rec, "task_id", "") or "")
    from nucleo.circuit import spec, verify as _verify
    e = spec.of_task(uid) or {}
    dw = e.get("done_when")
    if not dw:
        return {"ok": True, "result": {"met": None, "missing": [],
                                       "note": "this task declared no end state: declare it with report goal"}}
    try:
        met = _verify.check(dw)
        missing = [] if met else _verify.missing(dw)
    except Exception as ex:  # noqa: BLE001 — unreadable is None, never a failure
        logger.debug(f"task_files: verify unread ({ex!r})")
        met, missing = None, []
    return {"ok": True, "result": {"met": met, "missing": missing, "end_state": _verify.describe(dw),
                                   "note": "the circuit closes the task; report what you did and stop"}}
