"""The trash of appointments — a cancellation that does not ask is undone with `restore_meeting` (2026-10-05).

Tasks have had a trash since V2-748 (`tasklists._to_trash`): a removal that no longer asks needs a way back. An
appointment had none, so «cancel the architecture meeting» was final — and for a series it was worse, because the
three shapes of a cancellation are three different undos:

  · `delete` — the rows left the store; they come back VERBATIM minus what tied them to the old Google event and
    the old notice (a fresh event and a fresh notice are made, the way a new booking makes them);
  · `skip`   — one day of a series was skipped; the day leaves `repeat.skip` again;
  · `cut`    — a series was ended early; its `until` goes back to what it was.

Bounded like the tasks' trash: twenty entries, the oldest falls off. It reads and writes only the agenda's own store.
"""
from __future__ import annotations

import copy
import re
import time
import unicodedata

TRASH_MAX = 20
_KEY = "meetingTrash"
_TIES = ("googleId", "googleSeriesId", "reminder_id", "remindAt", "remindFor", "source", "etag", "htmlLink")


def _norm(s) -> str:
    s = unicodedata.normalize("NFD", str(s or ""))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip().lower()


def put(db: dict, kind: str, rows: list, **extra) -> None:
    """Remember what a cancellation took. Called with the rows it acted on: `delete` before they leave the store
    is not required (they are copied), `skip`/`cut` with the series rows and `day` / `until_before`."""
    if not rows:
        return
    entry = {"at": time.time(), "kind": kind, "label": str(rows[0].get("title") or ""),
             "rows": [copy.deepcopy(r) for r in rows], **extra}
    bin_ = db.setdefault(_KEY, [])
    bin_.append(entry)
    del bin_[:-TRASH_MAX]


def head(db: dict) -> dict | None:
    bin_ = db.get(_KEY) or []
    return dict(bin_[-1]) if bin_ else None


def _series(db: dict, row: dict) -> dict | None:
    return next((m for m in db.get("meetings", []) if isinstance(m.get("repeat"), dict)
                 and str(m.get("date") or "") == str(row.get("date") or "")
                 and _norm(m.get("title")) == _norm(row.get("title"))), None)


def restore(db: dict, payload: dict) -> dict:
    """Bring back the last cancellation, or the latest whose title contains `title`/`what`. Never raises."""
    from . import data as _d
    bin_ = db.get(_KEY) or []
    if not bin_:
        return {"ok": False, "error": "the appointments trash is empty — nothing was cancelled that I can bring back"}
    want = _norm(payload.get("title") or payload.get("what") or "")
    idx = len(bin_) - 1
    if want:
        hits = [i for i, e in enumerate(bin_) if want in _norm(e.get("label"))]
        if not hits:
            return {"ok": False, "error": f"nothing called that in the trash; the last one cancelled was "
                                          f"«{bin_[-1].get('label')}»"}
        idx = hits[-1]
    entry = bin_.pop(idx)
    kind, back = entry.get("kind"), 0
    for row in entry.get("rows") or []:
        if kind == "skip":
            ser = _series(db, row)
            day = str(entry.get("day") or "")
            if ser is not None and day in (ser["repeat"].get("skip") or []):
                ser["repeat"]["skip"] = [x for x in ser["repeat"]["skip"] if x != day]
                _d.gcal.patch_google(ser)
                back += 1
        elif kind == "cut":
            ser = _series(db, row)
            if ser is not None:
                prev = str(entry.get("until_before") or "")
                if prev:
                    ser["repeat"]["until"] = prev
                else:
                    ser["repeat"].pop("until", None)
                _d.gcal.patch_google(ser)
                back += 1
        else:
            fresh = {k: v for k, v in row.items() if k not in _TIES}
            if not fresh.get("allDay") and fresh.get("startTime"):
                day = _d.recur.next_occurrence(fresh, _d._today()) or str(fresh.get("date") or "")
                jid, at = _d._schedule_reminder(str(fresh.get("title") or ""), day, fresh.get("startTime", ""))
                if jid:
                    fresh["reminder_id"], fresh["remindAt"] = jid, at
            _d.gcal.commit_meeting(db, fresh)
            back += 1
    return {"ok": True, "restored": back, "what": kind, "title": entry.get("label") or "",
            **({"day": entry["day"]} if entry.get("day") else {})}
