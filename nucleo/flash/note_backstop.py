"""nucleo/flash/note_backstop.py — the dated-note backstop's ONE decision, for both channels (V2-159 → 2026-10-10).

The backstop writes an appointment the turn promised and did not write (`reminder_guards.dated_note_backstop`).
Its window branch reads the obligation from an EARLIER turn of his, and is re-evaluated every turn — so it can
land long after the conversation has moved on. Measured 2026-10-10 (use case `agenda-appointment-lifecycle`, ES):

    t1 «Apúntame una revisión del coche … el 20 de octubre a las diez» → the model's add_meeting (it WAS written)
    t2 «ponla a las cinco»                                            → move_meeting
    t3 «al final anúlala»                                             → cancel_meeting (the row went to the trash)
    t4 «Perfecto, gracias. Nos vemos.»                                → the backstop re-read t1 and wrote it AGAIN

The cancelled appointment came back «confirmed» with a live notice for the 20th at 09:00. `already_in_agenda`
only looks at the rows still in the agenda on THAT day, so it saw neither the cancellation (the row is in the
trash) nor a move to another day. What he did with the appointment AFTER asking for it is his last word on it:
a cancelled appointment stays cancelled and a moved one stays where he moved it.

Both channels call `note_to_file` — the voice half used to skip even the same-day check, which is how a class of
defect survives: by diverging between the two (the «cablear en AMBOS» rule, kept by having one function).
"""
from __future__ import annotations

import time as _time

from nucleo.flash.text_norm import _content_words

#: How long a cancellation of his is remembered by the backstop on OTHER days than the row's own: one
#: conversation. On the appointment's own day the trash is always consulted.
WITHDRAWN_TTL_S = 1800


def _same(mine: set, title) -> bool:
    theirs = _content_words(str(title or ""))
    return bool(theirs) and len(mine & theirs) >= min(2, len(mine))


def already_handled(note: dict, db: dict | None = None, *, now: float | None = None) -> str:
    """Why this note must NOT be written ("in_agenda", "cancelled", "moved"), or "" to write it. Never raises."""
    try:
        from nucleo.flash import reminder_guards as _rg
        if db is None and _rg.already_in_agenda(note):
            return "in_agenda"
        if db is None:
            from widgets import store as _store
            db = _store.load("agenda") or {}
        mine = _content_words(str(note.get("title") or ""))
        if not mine:
            return ""
        day = str(note.get("date") or "")
        now = _time.time() if now is None else now
        for m in db.get("meetings") or []:
            if not isinstance(m, dict) or not _same(mine, m.get("title")):
                continue
            if str(m.get("date") or "") == day:
                return "in_agenda"
            # the SAME commitment on another day, the one the conversation is on: he moved it there
            f = db.get("focus") or {}
            if _same(mine, f.get("title")) and now - float(f.get("at") or 0) <= WITHDRAWN_TTL_S:
                return "moved"
        for entry in db.get("meetingTrash") or []:
            if not isinstance(entry, dict):
                continue
            recent = now - float(entry.get("at") or 0) <= WITHDRAWN_TTL_S
            for r in entry.get("rows") or []:
                if isinstance(r, dict) and _same(mine, r.get("title")) and (recent or str(r.get("date") or "") == day):
                    return "cancelled"
        return ""
    except Exception:  # noqa: BLE001 — fail-open, like `already_in_agenda`: backing a promise beats dropping it
        return ""


def note_to_file(spoken: str, operator_text: str, *, window=None, emit=None) -> dict | None:
    """The `add_meeting` payload the backstop should write now, or None. The title carries no date/time phrase
    (`widgets.agenda.title_when`) and the hour it said travels as `startTime`."""
    try:
        from nucleo.flash import reminder_guards as _rg
        note = _rg.dated_note_backstop(spoken, operator_text, window=window)
        if not note:
            return None
        from widgets.agenda import title_when as _tw
        title, hour = _tw.split_when(note.get("title") or "")
        note = {**note, "title": title}
        if hour:
            note["startTime"] = hour
        why = already_handled(note)
        if why:
            if emit is not None:
                emit("widget", "🗓️ backstop de cita no escrito — ya lo resolvió él", text=f"{why} · {title}"[:160],
                     role="system", extra={"id": "agenda", "act": "add_meeting", "backstop": True, "skipped": why})
            return None
        return note
    except Exception:  # noqa: BLE001 — a backstop never takes down a live turn
        return None
