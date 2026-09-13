"""details.py — what a meeting is MADE OF: the optional fields a payload may carry onto it (V2-685).

Extracted from `data.py`, which sat EXACTLY on the 900-line newborn ceiling, so the one line Google Meet
needed had nowhere to go. The architecture ratchet asks for a module and never for a higher number, and
never for a smaller diff either — so this is the module, and it is a cohesive one rather than a slice cut
to fit: everything here answers the same question, and all of it is pure (a dict in, a dict mutated, no
store, no network, no clock).

The rule every applier in this file obeys, and the reason they live together: **only keys PRESENT in the
payload are touched.** `_apply_details` is shared by the create and the edit paths, so an edit that names
one field must not blank the others — and for Meet that asymmetry is the expensive one, because nobody
looks at a field they did not just edit.
"""
from __future__ import annotations

import re
import unicodedata


def _strip_accents(s: str) -> str:
    """Local on purpose: this module imports nothing from `data.py`, which imports IT. Two lines of NFKD
    beat an import cycle papered over with a lazy import (the hidden-coupling ratchet counts those)."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


#: What a payload may call a video call. `meet` is the manifest's name; the other two are what a model
#: writes when it paraphrases, and an unambiguous natural alias must not cost the fact (V2-341).
_MEET_KEYS = ("meet", "videocall", "conference")


def apply_meet(meeting: dict, payload: dict) -> None:
    """Carry the Google Meet flag from a payload onto a meeting — and ONLY when the payload names it.

    V2-685. A Meet link is an ATTRIBUTE of an appointment, not a second thing to create: it is
    `conferenceData` on the Google event, minted from the calendar scope the connector already holds. That
    is why it rides `add_meeting`/`update_meeting` instead of getting a tool of its own — the model already
    has the tool that creates appointments, and what it lacked was knowing that one argument turns one into
    a video meeting.

    ⚠️ Absent from the payload means UNTOUCHED, never cleared — see this module's header for why that
    direction is the costly one.
    """
    for key in _MEET_KEYS:
        if key not in payload:
            continue
        v = payload.get(key)
        want = v if isinstance(v, bool) else str(v or "").strip().lower() not in ("", "0", "false", "no")
        if want:
            meeting["meet"] = True
        else:
            meeting.pop("meet", None)
            meeting.pop("meetLink", None)
        return


_PENDING_RE = re.compile(r"\b(?:pendiente|pending|tentative|provisional|maybe|quiza\w*|esperando|waiting)\b"
                         r"|\b(?:sin|no|not|todavia\s+no|aun\s+no)\b[^.]{0,20}\bconfirm",
                         re.I)
_CONFIRMED_RE = re.compile(r"\b(?:confirm\w*|aceptad\w*|acepta\w*|accepted|cerrad\w*|ok|okay|si|yes)\b", re.I)


def _norm_status(raw) -> str:
    """A spoken status ('ya me lo ha confirmado', 'sigue pendiente') → 'confirmed' | 'pending' | ''.
    Unknown words return '' rather than a guess: a wrong status is a claim about somebody else's answer."""
    n = _strip_accents(str(raw or "").strip().lower())
    if not n:
        return ""
    if _PENDING_RE.search(n):
        return "pending"
    return "confirmed" if _CONFIRMED_RE.search(n) else ""


def _norm_attendees(raw) -> list:
    """Attendees as a list of NAMES. Accepts a list, a comma/'y'-separated sentence, or a bare COUNT
    ('somos cuatro' → four unnamed seats), because the operator often knows how many before who."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        n = max(0, min(200, int(raw)))
        return [""] * n
    if isinstance(raw, list):
        return [str(x).strip()[:60] for x in raw if str(x).strip()][:50]
    s = str(raw or "").strip()
    if not s:
        return []
    if s.isdigit():
        return [""] * max(0, min(200, int(s)))
    parts = re.split(r"\s*(?:,|;|\+|\by\b|\band\b|&)\s*", s)
    return [p.strip()[:60] for p in parts if p.strip()][:50]


def _apply_details(meeting: dict, payload: dict) -> None:
    """Copy the optional descriptive fields of a meeting from a payload onto it. Shared by the create and
    the edit paths so the two can never disagree about what a meeting is made of. Only keys PRESENT in the
    payload are touched — an edit that names one field must not blank the others."""
    if "notes" in payload or "details" in payload:
        notes = str(payload.get("notes") or payload.get("details") or "").strip()
        if notes:
            meeting["notes"] = notes[:500]
        else:
            meeting.pop("notes", None)
    if "location" in payload or "place" in payload:
        loc = str(payload.get("location") or payload.get("place") or "").strip()
        if loc:
            meeting["location"] = loc[:160]
        else:
            meeting.pop("location", None)
    if "category" in payload:
        cat = str(payload.get("category") or "").strip().lower()
        if cat:
            meeting["category"] = cat[:40]
        else:
            meeting.pop("category", None)
    apply_meet(meeting, payload)
    for key in ("attendees", "people", "with"):
        if key in payload:
            who = _norm_attendees(payload.get(key))
            if who:
                meeting["attendees"] = who
            else:
                meeting.pop("attendees", None)
            break
    if "status" in payload or "confirmed" in payload:
        if "confirmed" in payload and "status" not in payload:
            st = "confirmed" if payload.get("confirmed") else "pending"
        else:
            st = _norm_status(payload.get("status"))
        if st:
            meeting["status"] = st
    if payload.get("allDay") or payload.get("all_day"):
        meeting["allDay"] = True
        meeting.pop("startTime", None)
        meeting.pop("endTime", None)
