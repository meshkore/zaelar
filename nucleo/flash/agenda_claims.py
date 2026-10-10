"""nucleo/flash/agenda_claims.py — «I've removed it from your agenda» is backed by the cancellation (2026-10-10).

Measured 2026-10-10 (use case `agenda-appointment-lifecycle`, EN): after writing and moving «Car service at the
garage», «You know what, cancel it» was answered «Okay, I've removed it from your agenda.» with NO call
(`pedido=[]`, action=chat). The appointment and its notice stayed. The promise repair never ran: the screen verdict
read `none` at 0.56, the late catalogue named `contactos` at 0.32, so no card was named and the door stayed shut —
and `reply_promise` reads a CLAIM («I've removed») as `none`, which is right for a promise detector and is exactly
why a claim of a finished removal needs its own backing.

The consequence is bounded, not the judgement: this only ever executes the agenda's OWN declared, reversible
`cancel_meeting` (a cancellation goes to the trash and `restore_meeting` brings it back, CRIT-C3), only on the ONE
appointment the conversation is on or the one his words name, only when his words ordered a removal AND the reply
claims it was done. A removal of a list row, a song or a notice is never read as an appointment, and a reply that
asks or refuses is left alone. Both channels call `cancel_call` — one decision, so they cannot diverge.
"""
from __future__ import annotations

import re
import time as _time

from nucleo.flash.text_norm import _content_words, _norm_txt

#: How long after the appointment was last touched a bare «cancel it» with an unspecific reply still means it.
#: A reply that names the agenda or a date, or an order that names the appointment, needs no such window beyond
#: the agenda's own focus (`widgets.agenda.edit.FOCUS_TTL_S`).
BARE_FOCUS_S = 180

_ORDER_RE = re.compile(
    r"\b(?:anul|cancel|qu[ií]t(?:a|al[ao]|ar|amel[ao]|el[ao])\b|borr|elimin|suprim|remove|delete|drop|scrap|get\s+rid\s+of|call\s+(?:it\s+|that\s+)?off|"
    r"take\s+(?:it|that)\s+off)\w*", re.I)
_CLAIM_RE = re.compile(
    # EN — a finished removal: «I've removed it», «it's been cancelled», «that's deleted», «removed it from…»
    r"\b(?:i'?ve|i\s+have|it'?s|it\s+is|that'?s|it\s+has|has)\s+(?:now\s+)?(?:been\s+)?"
    r"(?:removed|cancell?ed|deleted|taken\s+(?:it\s+)?off|cleared|scrapped|dropped)\b|"
    r"\b(?:removed|cancell?ed|deleted)\s+(?:it|that|the\s+\w+)\b|"
    # ES — «la quito», «la he quitado», «te la anulo», «queda anulada», «cancelada»
    r"\b(?:te\s+)?(?:la|lo)\s+(?:he\s+)?(?:quit|borr|elimin|anul|cancel)(?:o|ado)\b|"
    r"\b(?:queda|esta|ha\s+sido|quedo)\s+(?:anulad|cancelad|eliminad|borrad|quitad)[oa]\b|"
    r"^\s*(?:vale,?\s+|ok(?:ay)?,?\s+)?(?:anulad|cancelad|eliminad|borrad|quitad)[oa]\b|"
    # a bare completion ack on a removal order
    r"^\s*(?:vale,?\s+|ok(?:ay)?,?\s+)?(?:hecho|listo|done|all\s+done)\s*[.!]?\s*$", re.I)
_NEGATED_RE = re.compile(r"\b(?:no|not|never|cannot|can'?t|couldn'?t|haven'?t|didn'?t|won'?t|unable|todavia|yet)\b",
                         re.I)
# Not an appointment: a list row, a task, a song, a message, a notice. Read in his words AND in the reply.
_OTHER_RE = re.compile(
    r"\b(?:lista|list|tarea|task|compra|shopping|item|fila|row|cancion|song|musica|music|video|mensaje|message|"
    r"correo|email|mail|nota|note|foto|photo|contacto|contact)s?\b", re.I)
# A notice is its own thing in HIS words («cancel the reminder» is `cancel_reminder`); in the reply it is only the
# alarm going with the appointment («removed it and its reminder»), which is what a cancellation does (V2-473).
_NOTICE_RE = re.compile(r"\b(?:recordatorio|reminder|aviso|alarma|alarm|alerta|alert)s?\b", re.I)
_AGENDA_RE = re.compile(r"\b(?:agenda|calendar|calendario|cita|appointment|meeting|reunion|evento|event)s?\b|"
                        r"\b\d{1,2}\s+de\s+[a-z]+\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}\b",
                        re.I)


# «cancel the flight» names SOMETHING: when it is not an appointment of his, the one in focus is not it either. A
# pronoun («cancel it», «anúlala») or the agenda's own nouns («cancel the appointment») name the one in focus.
_REF_RE = re.compile(r"\b(?:anul|cancel|borr|elimin|suprim|quit|remove|delete|drop|scrap)\w*\s+(?:the|my|our|this|"
                     r"that|el|la|los|las|mi|mis|esa|ese|esta|este)\s+(\w+)", re.I)
_GENERIC = frozenset({"appointment", "meeting", "one", "event", "booking", "cita", "reunion", "evento", "reserva",
                      "entry", "thing", "plan"})


def _names_something(said: str) -> bool:
    m = _REF_RE.search(said)
    return bool(m) and m.group(1).lower() not in _GENERIC


def _named(db: dict, words: set) -> dict | None:
    """The ONE upcoming appointment his words name by its title, or None (none, or more than one)."""
    if not words:
        return None
    hits = []
    for m in db.get("meetings") or []:
        theirs = _content_words(str((m or {}).get("title") or ""))
        if theirs and len(words & theirs) >= min(2, len(theirs)):
            hits.append(m)
    titles = {str(m.get("title") or "").strip().lower() for m in hits}
    return hits[0] if len(titles) == 1 else None


def _in_focus(db: dict, now: float, max_age: float) -> dict | None:
    f = db.get("focus") or {}
    if not f.get("title") or now - float(f.get("at") or 0) > max_age:
        return None
    want = str(f["title"]).strip().lower()
    return next((m for m in db.get("meetings") or [] if str((m or {}).get("title") or "").strip().lower() == want),
                None)


def cancel_call(operator_text: str, reply: str, db: dict | None = None, *, now: float | None = None) -> dict | None:
    """`{widget_id: "agenda", action: "cancel_meeting", payload}` when the reply CLAIMS a removal his words ordered
    and no call made it, else None. Never raises."""
    try:
        said, words = _norm_txt(operator_text), _norm_txt(reply)
        if not said.strip() or not words.strip() or said.lstrip().startswith("[sistema]"):
            return None
        if "?" in reply or not _ORDER_RE.search(said) or not _CLAIM_RE.search(words) or _NEGATED_RE.search(words):
            return None
        if _OTHER_RE.search(said) or _NOTICE_RE.search(said) or _OTHER_RE.search(words):
            return None
        if db is None:
            from widgets import store as _store
            db = _store.load("agenda") or {}
        now = _time.time() if now is None else now
        from widgets.agenda import edit as _edit
        target = _named(db, _content_words(said) - {"cancel", "cancela", "anula", "quita", "borra", "remove", "delete"})
        if target is None and _names_something(said):
            return None                         # he named something that is not one of his appointments
        if target is None:
            specific = bool(_AGENDA_RE.search(words) or _AGENDA_RE.search(said))
            target = _in_focus(db, now, _edit.FOCUS_TTL_S if specific else BARE_FOCUS_S)
        if target is None or not str(target.get("title") or "").strip():
            return None
        payload = {"title": str(target["title"])}
        if not isinstance(target.get("repeat"), dict) and target.get("date"):
            payload["date"] = str(target["date"])   # a series keeps its own question (one day, or all of it?)
        return {"widget_id": "agenda", "action": "cancel_meeting", "payload": payload}
    except Exception:  # noqa: BLE001 — a backing must never take down a live turn
        return None
