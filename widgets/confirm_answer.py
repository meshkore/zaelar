"""widgets/confirm_answer.py — the card's Yes/No button answers the question its act waits on (V2-857 phase 3).

An irreversible data-op waits for his yes on the request's ROW (`nucleo/request/consent_ask`): the button answers THAT
question — the same one the voice answers through the brief — choosing its declared yes or no, so one act runs per
answer whoever answered first (`inline_ask.take`). None when no act of the card waits on a row: the caller keeps its
in-memory path (a card's delete or restore, which have no row yet).
"""
from __future__ import annotations

from fastapi.responses import JSONResponse


async def answer_row(wid: str, ok: bool, emit_confirmed) -> JSONResponse | None:
    from nucleo.request import consent_ask
    a = consent_ask.open_for_widget(wid)
    if a is None:
        return None
    from nucleo.cli import worker_api
    opts = a.get("options") or ["yes", "no"]
    if not await worker_api.answer_task(a["task_id"], a["ask_id"], opts[0 if ok else 1]):
        return JSONResponse({"ok": False, "error": "no hay confirmación pendiente"}, status_code=409)
    if ok:
        emit_confirmed(wid, str(a.get("question") or "")[:60])
    return JSONResponse({"ok": True, "id": wid, "row": a["task_id"], "ask_id": a["ask_id"],
                         **({"cancelled": True} if not ok else {})})
