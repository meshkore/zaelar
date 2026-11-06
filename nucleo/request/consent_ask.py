"""nucleo/request/consent_ask.py — a card's irreversible act waits for his yes ON ITS ROW (V2-857 phase 3).

The question used to live in this process's memory (`widgets.confirm._PENDING`, 90 s) and its yes was read by a word
list before the brief: a restart or a barge-in lost it, and «ok, book it» once sent a mail. Now it is one more
durable question of the one asker (`inline_ask.held` → `circuit/asker`): the request's inline row waits with its
`ask_id`, the act is retained on the row, the two answers are DECLARED candidates the brief picks (`worker_api_bind`:
`#0` yes, `#1` no) and the screen shows as buttons, the card's own button answers the same `ask_id`
(`widgets/confirm_answer.py`), and the yes re-runs the act through its own door once (`inline_ask.rerun`, `take`).
"""
from __future__ import annotations

from nucleo.request import base, note
from nucleo.request.inline_ask import held


def yes_no() -> list[str]:
    """The two declared answers to a consent question, in the interface's language (`answer_yes`, `answer_no`): the
    candidates the binding verdict picks among (`<ask_id>#0` is the yes) and the screen's two buttons."""
    try:
        from i18n import langs
        spec = langs.current_language()
        return [str(spec.answer_yes or "yes"), str(spec.answer_no or "no")]
    except Exception as e:  # noqa: BLE001
        note(e)
        return ["yes", "no"]


def ask_consent(wid: str, action: str, payload: dict | None, question: str, *, text: str = "") -> tuple[str, str]:
    """An irreversible act of a card (`confirm:true`, or the one consent rule's ASK_CONSENT) waits for his yes ON ITS
    ROW through the one asker (V2-857 phase 3). It used to wait in this process's memory (`widgets.confirm._PENDING`,
    90 s) and its yes was read by a word list before the brief: a restart or a barge-in lost the question, and «ok,
    book it» sent a mail. Now the request's inline row (`request.model.opened`) waits with its `ask_id`, the act is
    retained on the row, the two answers are DECLARED candidates the brief picks (`worker_api_bind`: `#0` yes,
    `#1` no) and the screen shows as buttons, and the yes re-runs the act through its own door (`rerun`). Returns
    `(row, ask_id)`, or `("", "")` when no row could be opened — the caller then keeps the act's old gate."""
    try:
        from nucleo.request import model as _rq
        row = _rq.opened(wid, action, text=text)
        if not row:
            return "", ""
        ask_id = held(row, wid, action, payload, {"ok": False, "consent": "ask_consent"}, question=question,
                      options=yes_no())
        if not ask_id:
            return "", ""
        try:
            from voice.observer import emit
            emit("task", "⚠️ an irreversible act waits for his yes on its row", role="system",
                 text=f"{base(wid)}:{action} · {question[:120]}",
                 extra={"cat": "flash", "task_id": row, "ask_id": ask_id, "widget": base(wid), "action": action,
                        "consent": "ask_consent"})
        except Exception as e:  # noqa: BLE001
            note(e)
        return row, ask_id
    except Exception as e:  # noqa: BLE001 — a question that could not reach its row keeps the old gate
        note(e)
        return "", ""


def open_for_widget(wid: str) -> dict | None:
    """The open consent question an act of card `wid` waits on (its row, ask_id and options), or None — what the
    card's own Yes/No button answers (`POST /widgets/{id}/confirm`), so the button and the voice answer ONE question."""
    try:
        from nucleo.circuit import asker
        from nucleo.cli import worker_api
        for a in sorted(worker_api.open_asks(), key=lambda a: -int(a.get("since") or 0)):
            art = asker.artefact(a["task_id"])
            if art.get("inline") and art.get("consent") == "ask_consent" \
                    and base((art.get("retained") or {}).get("widget")) == base(wid):
                return {**a, "options": [str(o) for o in (art.get("options") or [])]}
    except Exception as e:  # noqa: BLE001
        note(e)
    return None
