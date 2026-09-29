"""A message that cites a meeting carries the AGENDA's time (V2-776 K1, 2026-09-29).

Demo pass 56: «ok book it» (16:00-16:45) → «move it half an hour later» (16:30) → «send ethan a telegram with the
new time» → the model wrote «now at 5:00 PM» from memory, and a real Telegram went out with a false time. The
model composes the text of a send; the ENGINE knows the meeting. Deterministic and narrow: the last agenda
mutation of the conversation names the meeting, the text shares a word with that meeting's title, and every
clock time in the text becomes the agenda's — start first, end second when the text has a range. Anything
less certain (no meeting in the window, no shared word, no clock time) leaves the text untouched. Never a
question: he asked to send.
"""
from __future__ import annotations

import re

#: a clock time the text CITES: 12 h with am/pm, or 24 h with minutes. A bare «at 4» is not one (too many
#: numbers look like it), so it is never touched.
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)\b|\b([01]?\d|2[0-3]):([0-5]\d)\b", re.I)
_RANGE_JOIN_RE = re.compile(r"^\s*(?:–|-|—|to|a|hasta)\s*$", re.I)
_WORD_RE = re.compile(r"[^\W\d_]{4,}", re.U)
_STOP = {"with", "para", "sobre", "about", "meeting", "reunión", "reunion", "call", "catch", "tomorrow", "mañana"}
_MEETING_ACTIONS = ("add_meeting", "move_meeting", "update_meeting")


def _words(s: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(s or "")} - _STOP


def _named(payload: dict) -> str:
    return str(payload.get("title") or payload.get("item") or payload.get("name") or "").strip()


def _meeting_of(ops: list, meetings: list) -> dict | None:
    """The meeting the conversation is about: the newest agenda mutation of the window that names one."""
    for op in reversed(list(ops or [])):
        if str(op.get("wid") or "") != "agenda" or str(op.get("action") or "") not in _MEETING_ACTIONS:
            continue
        name = _named(op.get("payload") or {}).lower()
        if not name:
            continue
        for m in meetings or []:
            title = str(m.get("title") or "").strip().lower()
            if title and (title == name or name in title or title in name):
                return m
    return None


def _fmt(hhmm: str, twelve: bool) -> str:
    h, m = (int(x) for x in str(hhmm).split(":")[:2])
    if not twelve:
        return f"{h:02d}:{m:02d}"
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def _cited(text: str) -> list[dict]:
    """Every clock time in the text, with its span and whether it was written in 12 h style. A range's first
    half («4:00–4:45 PM») inherits the second half's suffix."""
    out = []
    for m in _TIME_RE.finditer(text or ""):
        if m.group(1) is not None:
            out.append({"span": m.span(), "twelve": True, "suffix": bool(m.group(3))})
        else:
            out.append({"span": m.span(), "twelve": False, "suffix": False})
    for i in range(len(out) - 1):
        a, b = out[i], out[i + 1]
        if _RANGE_JOIN_RE.match(text[a["span"][1]:b["span"][0]]):
            a["range_with"] = i + 1
            if b["twelve"] and b["suffix"]:
                a["twelve"] = True
    return out


def align(text: str, ops: list, meetings: list) -> tuple[str, str]:
    """`(text with the agenda's time, why)` — or `(text, "")` when nothing certain says it should change."""
    text = str(text or "")
    cited = _cited(text)
    if not cited:
        return text, ""
    meeting = _meeting_of(ops, meetings)
    if not meeting or not (_words(str(meeting.get("title") or "")) & _words(text)):
        return text, ""
    start, end = str(meeting.get("startTime") or ""), str(meeting.get("endTime") or "")
    if not re.match(r"^\d{1,2}:\d{2}$", start):
        return text, ""
    first = cited[0]
    pieces, changed = [], False
    replacements = {0: _fmt(start, first["twelve"])}
    if "range_with" in first and re.match(r"^\d{1,2}:\d{2}$", end):
        replacements[first["range_with"]] = _fmt(end, cited[first["range_with"]]["twelve"])
    # a 12 h range keeps its suffix on the second half only («4:30–5:15 PM»)
    if "range_with" in first and first["twelve"] and not first["suffix"]:
        replacements[0] = replacements[0].split(" ")[0]
    pos = 0
    for i, c in enumerate(cited):
        if i in replacements:
            a, b = c["span"]
            if text[a:b] != replacements[i]:
                changed = True
            pieces.append(text[pos:a]); pieces.append(replacements[i]); pos = b
    pieces.append(text[pos:])
    if not changed:
        return text, ""
    why = f"«{meeting.get('title')}» {meeting.get('date') or ''} {start}" + (f"-{end}" if end else "")
    return "".join(pieces), why.strip()


# ── The door both channels take ──────────────────────────────────────────────────────────────────────────────
_SEND_ACTIONS = ("send_to", "forward", "reply", "draft", "send_draft")


def _recent_ops() -> list:
    try:
        from nucleo import done_ops
        return done_ops.recent()
    except Exception:  # noqa: BLE001
        return []


def _meetings() -> list:
    try:
        from widgets.agenda import data as _agenda
        return list((_agenda.load_db() or {}).get("meetings") or [])
    except Exception:  # noqa: BLE001
        return []


def align_payload(wid: str, action: str, payload: dict) -> tuple[dict, str]:
    """The payload a messaging send should run with. `(payload, why)`; `why` is empty when nothing changed."""
    try:
        if str(wid or "").split("::")[0].strip().lower() != "mensajeria" or str(action or "") not in _SEND_ACTIONS:
            return payload, ""
        text = str((payload or {}).get("text") or "")
        if not text:
            return payload, ""
        new, why = align(text, _recent_ops(), _meetings())
        if not why:
            return payload, ""
        return {**payload, "text": new}, why
    except Exception:  # noqa: BLE001 — never take down a send over a courtesy
        return payload, ""
