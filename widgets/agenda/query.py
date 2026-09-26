"""query.py — the agenda ANSWERING A QUESTION, instead of handing over its first page (V2-704).

`data.prompt_digest()` is the always-on summary: it rides every turn's prompt while the card is open, so it is
bounded to the next twelve appointments and ends in «… y N citas más». That is right for what it is and wrong
for a question — «¿a qué hora es lo del dentista?» about the fifty-fifth appointment gets a block that does not
contain it, and a model reading a block whose first lines claim to be the agenda will say there is no such
appointment. Exactly the shape of the contacts incident this batch is named after: a summary answering as if it
were the record.

So a QUESTION gets its own door: the rows that MATCH it, wherever they are in the calendar, with the fields the
digest trims. The seam is `data.read_query(question)`, declared in `nucleo/flash/widget_read.py` and generic —
nothing there knows this module exists.

Written as its own file rather than inside `data.py` because that file is already over the architecture
ratchet's ceiling, and the standing instruction is to extract, never to grow it.
"""
from __future__ import annotations

import re
import unicodedata as _ud

#: How many matches an answer may carry. Past this the honest reply is a count plus the nearest few — reading
#: forty appointments out loud answers nothing.
_MAX_ROWS = 8

#: Words that are scaffolding, not subject. A question is mostly these, and matching on them would return the
#: whole calendar — which is what the summary already does, and the reason this door exists.
_STOP = {
    "que", "qué", "cual", "cuál", "cuando", "cuándo", "donde", "dónde", "como", "cómo", "quien", "quién",
    "hora", "horas", "dia", "día", "dias", "días", "fecha", "cita", "citas", "reunion", "reunión", "reuniones",
    "tengo", "tienes", "tiene", "hay", "es", "son", "esta", "está", "este", "esta", "ese", "esa", "eso",
    "del", "de", "la", "el", "los", "las", "un", "una", "y", "o", "con", "para", "por", "en", "a", "al",
    "mi", "me", "se", "lo", "su", "sobre", "acerca", "dime", "dame",
    "what", "when", "where", "which", "who", "time", "date", "day", "days", "meeting", "meetings",
    "appointment", "appointments", "event", "events", "calendar", "agenda", "the", "a", "an", "is", "are",
    "was", "were", "do", "does", "did", "have", "has", "i", "my", "of", "on", "at", "in", "for", "with",
    "and", "or", "about", "tell", "show", "give", "next", "any", "there",
}


def _norm(s) -> str:
    s = _ud.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not _ud.combining(c))


def _terms(question: str) -> list[str]:
    """The words a question is actually ASKING ABOUT. A bare number is never one: «2026» sat in the haystack of
    EVERY row (its date), so a question about one afternoon came back «7 appointments match» (V2-773 audit).
    Dates are read by `_dates_in` and scope the answer instead."""
    words = [w for w in re.split(r"[^\wÁÉÍÓÚÜÑáéíóúüñ]+", _norm(question)) if len(w) > 2 and not w.isdigit()]
    return [w for w in dict.fromkeys(words) if w not in _STOP][:8]


_ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_RELATIVE = (
    (re.compile(r"\bpasado ma[nñ]ana\b|\bday after tomorrow\b"), 2),
    (re.compile(r"\btomorrow\b|(?<!por la )(?<!de la )(?<!esta )(?<!por )(?<!pasado )\bma[nñ]ana\b"), 1),
    (re.compile(r"\btoday\b|\bhoy\b"), 0),
    (re.compile(r"\byesterday\b|\bayer\b"), -1),
)


def _dates_in(question: str) -> list[str]:
    """The DAYS a question is about: ISO dates written in it, and today/tomorrow/yesterday resolved against
    the clock. A question that names a day is answered with that day's record — all of it, or its emptiness —
    never with whatever rows happen to share a word with it."""
    q = _norm(question)
    found = list(dict.fromkeys(_ISO_DATE.findall(q)))
    import datetime as _dt
    try:
        base = _dt.date.fromisoformat(_today())
    except ValueError:
        return found
    for pat, delta in _RELATIVE:
        if pat.search(q):
            d = (base + _dt.timedelta(days=delta)).isoformat()
            if d not in found:
                found.append(d)
    return found


def _on_day(m: dict, day: str) -> bool:
    if isinstance(m.get("repeat"), dict):
        from . import recur
        return recur.next_occurrence(m, day) == day
    return str(m.get("date") or "") == day


def _hits(terms: list[str], hay: str) -> int:
    """How many of the question's words this appointment carries.

    Not plain containment: the operator and his calendar do not always speak the same language. His calendar
    holds «Dentist» (Google, in English) and he asks «¿a qué hora es lo del dentista?» — a substring test finds
    nothing and the answer becomes «no tienes nada del dentista», which is false and sounds certain. A shared
    five-letter prefix covers that whole family (dentist/dentista, doctor/doctora, meeting/meetings,
    reunion/reuniones) without inventing a stemmer per language, and five is long enough that it does not start
    matching unrelated words.
    """
    n = 0
    words = hay.split()
    for t in terms:
        if t in hay:
            n += 1
            continue
        if len(t) >= 5 and any(w.startswith(t[:5]) or t.startswith(w[:5]) for w in words if len(w) >= 5):
            n += 1
    return n


def _haystack(m: dict) -> str:
    """Everything about one appointment a question could name — including WHO is coming, because «¿cuándo
    quedé con Marta?» names a person, not a title."""
    parts = [m.get("title"), m.get("location"), m.get("notes"), m.get("date"),
             " ".join(str(w) for w in (m.get("attendees") or []))]
    return _norm(" ".join(str(p or "") for p in parts))


def _row(m: dict) -> str:
    hour = "todo el día" if m.get("allDay") else str(m.get("startTime") or "")
    row = f"· {m.get('date', '?')} {hour} «{m.get('title', 'Cita')}»"
    if m.get("endTime") and not m.get("allDay"):
        row += f"–{m['endTime']}"
    if m.get("location"):
        row += f" en {str(m['location'])[:80]}"
    who = [str(w) for w in (m.get("attendees") or []) if str(w).strip()]
    if who:
        row += f" · con {', '.join(who[:8])}"
    if m.get("status") == "pending":
        row += " · SIN confirmar por la otra parte"
    elif m.get("status") == "confirmed" and who:
        row += " · confirmada"
    for label, key in (("aviso", "remindAt"), ("enlace", "meetUrl"), ("enlace", "hangoutLink")):
        if m.get(key):
            row += f" · {label} {m[key]}"
            break
    if isinstance(m.get("repeat"), dict):                    # V2-769 — one row, many days: say which
        from . import recur
        row += f" · SE REPITE {recur.describe(m['repeat'])}"
        nxt = recur.next_occurrence(m, _today())
        row += f" · próxima {nxt}" if nxt else " · ya no quedan días"
    if m.get("notes"):
        row += f" — {str(m['notes'])[:200]}"
    return row


def _today() -> str:
    import time
    return time.strftime("%Y-%m-%d")


def read_query(question: str) -> str:
    """The appointments this question is about, wherever they sit in the calendar. "" when it names none.

    Deliberately searches the WHOLE calendar, past included: «¿cuándo fue lo del notario?» is a question about
    the agenda whether or not the date has gone by, and the summary — which only ever looks forward — is
    precisely what cannot answer it.
    """
    terms = _terms(question)
    days = _dates_in(question)
    if not terms and not days:
        return ""
    try:
        from . import data as _data
        meets = list((_data.load_db() or {}).get("meetings") or [])
    except Exception:                                    # noqa: BLE001 — a broken read answers nothing
        return ""
    if days:
        # A DAY is asked about: its whole record, in time order — «What do I have tomorrow afternoon?» over an
        # empty Sunday used to return every row of the calendar (the year matched them all) and the model
        # then read Monday's meetings as tomorrow's. An empty day is an answer, not an absence.
        rows = [m for m in meets if any(_on_day(m, d) for d in days)]
        if terms:
            named = [m for m in rows if _hits(terms, _haystack(m))]
            rows = named or rows
        rows.sort(key=lambda m: (str(m.get("date") or ""), not m.get("allDay"), str(m.get("startTime") or "")))
        when = ", ".join(days)
        if not rows:
            return f"Ningún compromiso el {when}: ese día está LIBRE en el calendario (esto SÍ es el registro completo del día)."
        return "\n".join([f"Citas del {when} — el registro COMPLETO de ese día ({len(rows)}):"]
                         + [_row(m) for m in rows[:_MAX_ROWS * 2]])
    if not meets:
        return ""
    scored = []
    for m in meets:
        hay = _haystack(m)
        hits = _hits(terms, hay)
        if hits:
            scored.append((hits, str(m.get("date") or ""), str(m.get("startTime") or ""), m))
    if not scored:
        return ""
    scored.sort(key=lambda t: (-t[0], t[1], t[2]))
    # THE SAME APPOINTMENT TWICE IS ONE APPOINTMENT, and saying how many copies there are beats repeating it.
    # The operator's calendar holds seven identical «renovar el seguro del coche» and five «Dentist» at the same
    # hour (a duplication whose cause is still open); without this, every one of the eight rows an answer may
    # carry went to one meeting and there was no room left for the others — and read out loud it would be the
    # same sentence seven times. Collapsing also makes the duplication AUDIBLE instead of hiding it.
    seen: dict = {}
    for hits, date, start, m in scored:
        key = (_norm(m.get("title")), date, start, bool(m.get("allDay")))
        if key in seen:
            seen[key][1] += 1
        else:
            seen[key] = [m, 1]
    rows = []
    for m, n in list(seen.values())[:_MAX_ROWS]:
        rows.append(_row(m) + (f"   ⚠️ el calendario guarda {n} copias IDÉNTICAS de esta cita" if n > 1 else ""))
    total = len(seen)
    head = ("La cita por la que se pregunta, del calendario ENTERO (esto SÍ es el registro):"
            if total == 1 else
            f"{total} citas del calendario encajan con lo que se pregunta"
            + (f" — las {len(rows)} más cercanas:" if total > len(rows) else ":"))
    return "\n".join([head] + rows)
