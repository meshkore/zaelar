"""widgets/agenda/when.py — a spoken date or hour, turned into one the calendar can store.

Extracted from `data.py` under the architecture ratchet (V2-744): that file sat at 899 of its 900-line
ceiling and the tasks section needed room in `apply_action`. The ratchet's answer to a file at its ceiling
is «extract a module, never raise the number», and this is the cohesive thing to cut — four pure functions
over strings with no state, no IO and no knowledge of what a meeting is.

It is also the half the TASKS section needs (V2-744): «apúntame comprar pan mañana» resolves its day the
same way an appointment does, and a second copy of this table is how «jueves» ends up meaning one thing in
the calendar and another in a list. Moved byte for byte; `data.py` re-exports every name, so
`invite.py`, `sweep.py` and every test that reaches `data._resolve_date` keep working unchanged.
"""
from __future__ import annotations

import re
import time as _t
import unicodedata


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _today() -> str:
    return _t.strftime("%Y-%m-%d")


# Relative spoken date/time normalization (V2-026). English joined in V2-639: the engine is multilingual
# (V2-613) and an EN operator says «tomorrow»/«monday» — a resolver that only hears Spanish silently files
# their appointment TODAY, which is the same class of lie as the defaulted write.
_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4,
             "sabado": 5, "sábado": 5, "domingo": 6,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
             "saturday": 5, "sunday": 6}


def _m2(hhmm) -> int:
    """'HH:MM' -> minutes; tolerant of junk (0)."""
    try:
        h, m = str(hhmm or "0:0").split(":")[:2]
        return int(h) * 60 + int(m)
    except Exception:  # noqa: BLE001
        return 0


def _resolve_date(raw: str) -> str:
    """Convert a spoken relative date (tomorrow, today, the day after tomorrow, a weekday, or already 'YYYY-MM-DD') into
    'YYYY-MM-DD'. Sensible default: today. This keeps a relative-date appointment correctly placed even when the
    model does not calculate the date itself."""
    import time as _t
    s = (raw or "").strip().lower()
    if not s:
        return _today()
    if len(s) >= 8 and s[:4].isdigit() and "-" in s:      # already comes as YYYY-MM-DD
        return s[:10]
    n = _strip_accents(s)
    if (_named := _calendar_date(n)):
        return _named
    today = _t.localtime()
    base = _t.mktime(today)
    day = 86400
    if "pasado manana" in n or "day after tomorrow" in n:
        return _t.strftime("%Y-%m-%d", _t.localtime(base + 2 * day))
    if "manana" in n or "tomorrow" in n:
        return _t.strftime("%Y-%m-%d", _t.localtime(base + day))
    if "hoy" in n or "today" in n:
        return _today()
    for name, wd in _WEEKDAYS.items():
        nn = _strip_accents(name)
        if nn in n:
            delta = (wd - today.tm_wday) % 7
            delta = delta or 7                             # weekday references mean the next matching day, not today
            return _t.strftime("%Y-%m-%d", _t.localtime(base + delta * day))
    return _today()


_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
           "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
           "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
           "september": 9, "october": 10, "november": 11, "december": 12}


def _calendar_date(n: str) -> str:
    """«el 14 de octubre», «October 14th», «14/10» → the next such day (V2-770). Before this, any date said by
    its NAME fell through to TODAY: «pásame el dentista al 14 de octubre» moved it to the day it was said."""
    import datetime as _dt
    m = re.search(r"\b(\d{1,2})\s*/\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?\b", n)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    else:
        mo = next((v for k, v in _MONTHS.items() if re.search(rf"\b{k}\b", n)), 0)
        m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th|º)?\b(?!\s*[:h.]\d)", n) if mo else None
        if not m:
            return ""
        d = int(m.group(1))
        y = (re.search(r"\b(20\d{2})\b", n) or [None, None])[1]
    t = _dt.date.today()
    year = (int(y) + (2000 if int(y) < 100 else 0)) if y else t.year
    try:
        day = _dt.date(year, mo, d)
    except ValueError:
        return ""
    if not y and day < t:
        day = day.replace(year=t.year + 1)
    return day.isoformat()


def _resolve_time(raw: str, default: str = "17:00") -> str:
    """Normalize a spoken time (natural language hour, meridiem, '17h', or '17:00') into 'HH:MM'. Defaults 1-7 without an
    explicit meridiem to afternoon, because appointments are more often requested for evening than early morning."""
    s = (raw or "").strip().lower()
    if not s:
        return default
    m = re.search(r"(\d{1,2})[:h\.](\d{2})", s)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"\b(\d{1,2})\b", s)
    if m:
        h = int(m.group(1))
        pm = any(w in s for w in ("tarde", "noche", "pm", "afternoon", "evening", "night"))
        am = any(w in s for w in ("manana", "mañana", "madrugada", "am", "morning"))
        if pm and h < 12:
            h += 12
        elif not am and 1 <= h <= 7:                       # bare 1-7 without am/pm -> afternoon
            h += 12
        return f"{h % 24:02d}:00"
    return default
