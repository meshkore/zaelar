"""nucleo/cli/worker_api_resume.py — an answer resumes THE session that asked, by id, re-briefed from its row.

V2-851 §3 (truth = row, session = cache). The worker's process ended after `ask`; its row keeps `session_id` (the
harness's resumable id) and `cwd` (a harness resumes by id but does not keep its working directory, §15e). An
answer relaunches that session — `--resume <session_id>` in the stored cwd — continuing the SAME row (`task_uid`, as
a relay does), and its first message is the re-brief built here from the row: where it was, what it waited for, the
question and his answer. The same path serves after a restart: nothing of it lives in RAM.
"""
from __future__ import annotations

from loguru import logger


def rebrief(row: dict, entry: dict) -> str:
    """The resumed session's first message, from the row and the question's artefact — never from the session."""
    title = str(row.get("title") or row.get("goal") or "").strip()[:160]
    lines = [f"[RESUME · task «{title}»] You are resuming THIS task where it stopped. Its row is the truth.",
             f"Step it was at: {str(row.get('phase') or '').strip()[:160] or 'unknown'}."]
    if str(row.get("waiting_for") or "") == "worker" or not entry:
        lines.append("Your process stopped before finishing; nothing was asked or answered. What you produced so far "
                     "is on the task.")
    else:
        lines += [f"It waited for: {str(row.get('waiting_for') or 'user_answer')}.",
                  f"Your question: «{str(entry.get('question') or row.get('ask') or '').strip()[:600]}»",
                  f"His answer: «{str(entry.get('answer') or '').strip()[:600]}»"]
    act = (entry.get("retained") or {}).get("action")
    if act:
        res = entry.get("result")
        lines.append(f"The act you asked to confirm ({act}) RAN; its result: {res}" if res is not None
                     else f"The act you asked to confirm ({act}) did NOT run: he did not confirm it.")
    lines.append("Confirm the state through the bridge before acting, then continue from that step.")
    return "\n".join(lines)


def context_for(row: dict, entry: dict, src: str = "answer") -> dict:
    """The escalation context that resumes `row`: same row, same session id, same cwd, the re-brief."""
    uid = str(row.get("id") or "")
    return {"src": src, "kind": str(row.get("kind") or "generic"), "task_uid": uid,
            "sheet": str(row.get("sheet") or ""), "surface": str(row.get("surface") or ""),
            "resume": {"answer": str(entry.get("answer") or ""), "native_sid": str(row.get("session_id") or ""),
                       "cwd": str(row.get("cwd") or ""), "rebrief": rebrief(row, entry), "brief_task": uid}}


def resume_soon(uid: str, entry: dict, src: str = "answer") -> int:
    """Relaunch the session of row `uid` with his answer. Returns the new dispatch id (0 if nothing was launched)."""
    try:
        from nucleo.circuit import ledger
        _ts = ledger.store()
        row = _ts.task_get(uid)
        if not row or str(row.get("state") or "") in _ts.DONE_STATES:
            return 0
        from nucleo.acts import errand as _esc
        tid = _esc.escalate_to_slowbrain(str(row.get("goal") or row.get("title") or ""),
                                         context=context_for(row, entry, src))
        logger.info(f"worker_api: answer resumes row {uid} (session {str(row.get('session_id') or '')[:12]}) → {tid}")
        return int(tid or 0)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker_api: could not resume row {uid}: {e!r}")
        return 0
