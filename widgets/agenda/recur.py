"""widgets/agenda/recur.py — a REPEATING appointment: one row with a rule, expanded wherever it is read (V2-769).

THE MEASUREMENT (operator's own agenda, 2026-09-25, session a96fdea7). He dictated two weekly appointments
running until June 2027 — «llevar a Abril a flauta travesera» on Thursdays 15:30-16:15 and «piano de Abril» on
Tuesdays 15:15-16:00. What the store held afterwards:

    {"title": "Llevar a Abril a flauta travesera", "date": "2026-10-01", ..., "category": "recursiva",
     "notes": "Todos los jueves de 15:30 a 16:15"}
    {"title": "Piano de Abril", "date": "2026-09-22", ..., "category": "familia"}

One date each. The first time the model had no field to say «every Thursday», so it smuggled the rule into
`category` and `notes`. The second time it DID send it — `recurrence: "weekly", repeatUntil: "2027-06-30"` —
and `add_meeting` dropped both keys without a word, the reply said «desde el 22 de septiembre hasta junio de
2027», and the week after next was empty. His words: *«es un poco un desastre manejar una simple agenda… no
solo poner un ítem un día, sino también hacerlo recursivo entre el período que yo te digo»*.

THE SHAPE. A series is ONE meeting row carrying

    "repeat": {"freq": "daily" | "weekly" | "monthly", "interval": 1,
               "days": [0..6]   (weekly only; Monday = 0),
               "until": "YYYY-MM-DD" | "",          (inclusive; "" = open-ended)
               "skip": ["YYYY-MM-DD", …]}           (occurrences cancelled one by one)

and its own `date` is the FIRST occurrence. Nothing stores the copies: every reader — the card's calendar, the
day planner, the digest the brain reads, the question door, the notice — asks this module which days the row
falls on. That is the one decision that keeps «cancel just this Thursday», «until when?» and «move it to 17:00»
edits of ONE row instead of a hunt through fifty-two.

Pure and stdlib-only (the agenda's `data.py` contract): dates in, dates out, no store, no clock unless given.
"""
from __future__ import annotations

import datetime as _dt
import re
import unicodedata

FREQS = ("daily", "weekly", "monthly")

#: The keys a caller may use for the rule. The model's own natural names are here on purpose — measured, it
#: sent `recurrence` + `repeatUntil` the first time it had anything to say it with — and a natural alias must
#: never cost the fact (the V2-341/V2-473 rule).
RULE_KEYS = ("repeat", "recurrence", "recurring", "rrule", "frequency", "freq", "repeats", "repetition",
             "every", "recurrente", "repetir")
UNTIL_KEYS = ("until", "repeatUntil", "repeat_until", "endDate", "end_date", "recurrenceEnd",
              "recurrence_end", "hasta", "untilDate")
DAYS_KEYS = ("days", "byDay", "by_day", "weekdays", "daysOfWeek", "dias")
INTERVAL_KEYS = ("interval", "everyN")
#: Every key this module reads — `data.py` counts a payload key as UNDERSTOOD when it is one of these.
ALL_KEYS = RULE_KEYS + UNTIL_KEYS + DAYS_KEYS + INTERVAL_KEYS

#: Hard ceiling on occurrences walked per expansion — a daily rule with no end, read over a decade, must
#: still return in microseconds.
_MAX_STEPS = 2000

_DAY_NAMES = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
              "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5,
              "sunday": 6, "mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6,
              "mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6,
              "lun": 0, "mar": 1, "mie": 2, "jue": 3, "vie": 4, "sab": 5, "dom": 6}
_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
           "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
           "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
           "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
_FREQ_WORDS = (("daily", ("daily", "diari", "cada dia", "todos los dias", "every day", "a diario", "day")),
               ("monthly", ("monthly", "mensual", "cada mes", "todos los meses", "every month", "month")),
               ("weekly", ("weekly", "semanal", "cada semana", "todas las semanas", "every week", "week",
                           "todos los", "todas las", "cada")))
_NONE_WORDS = ("none", "no", "never", "nunca", "ninguna", "ninguno", "once", "una vez", "false", "0", "off")


def _fold(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c)).strip()


def _date(s) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(str(s or "")[:10])
    except ValueError:
        return None


def _last_day(y: int, m: int) -> int:
    nxt = _dt.date(y + (m == 12), m % 12 + 1, 1)
    return (nxt - _dt.timedelta(days=1)).day


def parse_until(raw, today: _dt.date | None = None) -> tuple[str, bool]:
    """A spoken or written end date → ('YYYY-MM-DD', True); ('', True) for none given; ('', False) when it
    says something this cannot read — never a guess, because a wrong end date deletes months of a series.

    «junio de 2027» is the END of June: he said «hasta junio», and a series that stops on the 1st loses the
    four Tuesdays he meant."""
    s = _fold(raw)
    if not s:
        return "", True
    today = today or _dt.date.today()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return (m.group(0) if _date(m.group(0)) else ""), bool(_date(m.group(0)))
    m = re.fullmatch(r"(\d{4})-(\d{2})", s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return (f"{y:04d}-{mo:02d}-{_last_day(y, mo):02d}", True) if 1 <= mo <= 12 else ("", False)
    m = re.search(r"(\d{8})", s)                                   # RRULE UNTIL=20270630[T…]
    if m and _date(f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"):
        return f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}", True
    day = re.search(r"\b(\d{1,2})\b(?!\d)", s)
    year = re.search(r"\b(\d{4})\b", s)
    month = next((n for w, n in _MONTHS.items() if re.search(rf"\b{w}\b", s)), 0)
    if month:
        y = int(year.group(1)) if year else (today.year + (month < today.month))
        if day and not (year and day.group(1) == year.group(1)):
            d = int(day.group(1))
            return (f"{y:04d}-{month:02d}-{d:02d}", True) if 1 <= d <= _last_day(y, month) else ("", False)
        return f"{y:04d}-{month:02d}-{_last_day(y, month):02d}", True
    return "", False


def _days(raw) -> list[int]:
    if raw in (None, "", []):
        return []
    items = raw if isinstance(raw, (list, tuple)) else re.split(r"[,\s;/y]+|\band\b", _fold(raw))
    out: list[int] = []
    for it in items:
        if isinstance(it, int) and 0 <= it <= 6:
            out.append(it)
            continue
        w = _fold(it)
        if w.isdigit() and 0 <= int(w) <= 6:
            out.append(int(w))
            continue
        w = re.sub(r"^\d", "", w)                                   # RRULE «2TH» → «th»
        hit = _DAY_NAMES.get(w) if w in _DAY_NAMES else next(
            (n for k, n in _DAY_NAMES.items() if len(k) >= 5 and w.startswith(k[:5])), None)
        if hit is not None:
            out.append(hit)
    return sorted(set(out))


def _freq_of(s: str) -> str:
    f = _fold(s)
    for freq, words in _FREQ_WORDS:
        if any(w in f for w in words):
            return freq
    return ""


def parse(payload: dict, start_date: str, today: _dt.date | None = None) -> tuple[dict | None, str]:
    """The rule a write carries → (repeat, "") · (None, "") when it carries none · (None, why) when it carries
    one this cannot read. The third case is an ERROR on purpose: dropping a rule is how his Tuesdays vanished.

    Accepts the canonical dict, a bare word («weekly», «semanal», «todos los jueves»), a boolean with the
    rule's pieces beside it, and an RRULE string (FREQ=WEEKLY;BYDAY=TU;UNTIL=20270630)."""
    p = payload or {}
    raw = next((p[k] for k in RULE_KEYS if k in p and p[k] not in (None, "")), None)
    until_raw = next((p[k] for k in UNTIL_KEYS if p.get(k) not in (None, "")), None)
    days_raw = next((p[k] for k in DAYS_KEYS if p.get(k) not in (None, "", [])), None)
    interval_raw = next((p[k] for k in INTERVAL_KEYS if p.get(k) not in (None, "")), None)
    if raw is None and until_raw is None and days_raw is None:
        return None, ""
    freq = ""
    if isinstance(raw, dict):
        freq = _freq_of(raw.get("freq") or raw.get("frequency") or "")
        until_raw = raw.get("until") or raw.get("repeatUntil") or until_raw
        days_raw = raw.get("days") or raw.get("byDay") or days_raw
        interval_raw = raw.get("interval") or interval_raw
    elif isinstance(raw, bool):
        if not raw:
            return None, ""
    elif raw is not None:
        s = str(raw)
        if _fold(s) in _NONE_WORDS:
            return None, ""
        if "freq=" in s.lower():
            parts = dict(kv.split("=", 1) for kv in s.upper().replace("RRULE:", "").split(";") if "=" in kv)
            freq = _freq_of(parts.get("FREQ", ""))
            until_raw = parts.get("UNTIL") or until_raw
            days_raw = parts.get("BYDAY", "").lower() or days_raw
            interval_raw = parts.get("INTERVAL") or interval_raw
        else:
            freq = _freq_of(s)
            if not days_raw:
                days_raw = [d for d in _days(s)] or None
    if not freq and raw is None and not days_raw:
        # V2-771 — an END DATE with no rule and no weekdays is a SPAN, not a series: «Anna vacation, December 20
        # through January 4» is every day of that stretch. It fell to `weekly` below and showed on the 20th and
        # the 27th only. A weekly series names its day («every Tuesday») or its rule, and both still go to weekly.
        freq = "daily"
    if not freq:
        freq = "weekly" if (days_raw or raw is True or raw is None) else ""
    if freq not in FREQS:
        return None, (f"no entiendo cada cuánto se repite («{raw}») — manda `repeat` con freq daily, weekly "
                      f"o monthly, `days` (lunes…domingo) y `until` (YYYY-MM-DD)")
    until, ok = parse_until(until_raw, today)
    if not ok:
        return None, (f"no entiendo hasta cuándo se repite («{until_raw}») — manda `until` como YYYY-MM-DD "
                      f"(o «junio de 2027»)")
    try:
        interval = max(1, min(52, int(interval_raw or 1)))
    except (TypeError, ValueError):
        interval = 1
    rep: dict = {"freq": freq, "interval": interval, "until": until}
    if freq == "weekly":
        days = _days(days_raw)
        if not days:
            d0 = _date(start_date)
            days = [d0.weekday()] if d0 else []
        rep["days"] = days
    if until and _date(start_date) and until < start_date:
        return None, (f"la repetición acabaría ({until}) antes de empezar ({start_date}) — revisa `until`")
    return rep, ""


def first_on_or_after(rep: dict, start: str) -> str:
    """The first day ≥ `start` the rule lands on — a weekly series dictated on a Friday «los martes» starts
    on the next Tuesday, never on the Friday it was said."""
    d = _date(start)
    if not d or not rep:
        return start
    if rep.get("freq") == "weekly" and rep.get("days"):
        for i in range(7):
            if (d + _dt.timedelta(days=i)).weekday() in rep["days"]:
                return (d + _dt.timedelta(days=i)).isoformat()
    return start


def occurrences(m: dict, lo: str, hi: str) -> list[str]:
    """Every day in [lo, hi] (inclusive) this row falls on. A plain row answers its own date if inside."""
    rep = m.get("repeat") if isinstance(m.get("repeat"), dict) else None
    d0 = _date(m.get("date"))
    a, b = _date(lo), _date(hi)
    if not d0 or not a or not b:
        return []
    if not rep:
        return [d0.isoformat()] if a <= d0 <= b else []
    end = _date(rep.get("until")) or b
    b = min(b, end)
    skip = set(rep.get("skip") or [])
    iv = max(1, int(rep.get("interval") or 1))
    out: list[str] = []
    freq = rep.get("freq")
    if freq == "daily":
        k = max(0, ((a - d0).days + iv - 1) // iv)
        cur = d0 + _dt.timedelta(days=k * iv)
        for _ in range(_MAX_STEPS):
            if cur > b:
                break
            if cur >= d0 and cur.isoformat() not in skip:
                out.append(cur.isoformat())
            cur += _dt.timedelta(days=iv)
    elif freq == "weekly":
        days = set(rep.get("days") or [d0.weekday()])
        week0 = d0 - _dt.timedelta(days=d0.weekday())
        cur = max(a, d0)
        for _ in range(_MAX_STEPS):
            if cur > b:
                break
            if cur.weekday() in days and ((cur - week0).days // 7) % iv == 0 and cur.isoformat() not in skip:
                out.append(cur.isoformat())
            cur += _dt.timedelta(days=1)
    elif freq == "monthly":
        y, mo, i = d0.year, d0.month, 0
        for _ in range(_MAX_STEPS):
            if i % iv == 0:
                dd = _dt.date(y, mo, min(d0.day, _last_day(y, mo)))
                if dd > b:
                    break
                if dd >= a and dd.isoformat() not in skip:
                    out.append(dd.isoformat())
            y, mo, i = y + (mo == 12), mo % 12 + 1, i + 1
    return out


def occurs_on(m: dict, date: str) -> bool:
    return bool(date) and bool(occurrences(m, date, date))


def next_occurrence(m: dict, today: str) -> str:
    """The first day ≥ `today` this row falls on, or "" when it has none left."""
    if not isinstance(m.get("repeat"), dict):
        return str(m.get("date") or "") if str(m.get("date") or "") >= today else ""
    t = _date(today)
    if not t:
        return ""
    hi = (t + _dt.timedelta(days=800)).isoformat()
    for occ in occurrences(m, today, hi)[:1]:
        return occ
    return ""


def expand(meetings: list[dict], lo: str, hi: str) -> list[dict]:
    """The meeting list with every SERIES replaced by its occurrences in [lo, hi] — what a calendar draws.
    Plain rows pass through untouched (all of them: the card has always received every dated meeting).
    Each occurrence is a copy carrying `date` = that day and `seriesDate` = the row's own first day; the
    notice fields stay only on the occurrence they belong to."""
    out: list[dict] = []
    for m in meetings or []:
        if not isinstance(m.get("repeat"), dict):
            out.append(m)
            continue
        for occ in occurrences(m, lo, hi):
            c = dict(m)
            c["date"], c["seriesDate"] = occ, m.get("date")
            if not str(m.get("remindAt") or "").startswith(occ):
                c.pop("remindAt", None)
                c.pop("reminder_id", None)
            out.append(c)
    return out


def on_date(meetings: list[dict], date: str) -> list[dict]:
    """The rows (occurrences included) that fall on one day."""
    return expand([m for m in meetings or [] if isinstance(m.get("repeat"), dict) or m.get("date") == date],
                  date, date)


_WD = {"es": ["lunes", "martes", "miércoles", "jueves", "viernes", "sábados", "domingos"],
       "en": ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]}


def describe(rep: dict, lang: str = "es") -> str:
    """The rule in one phrase, for what the BRAIN reads (digest, query) — «todos los martes hasta el
    2027-06-30». The card paints its own label from the translated bundle; this is prose for the model."""
    if not isinstance(rep, dict):
        return ""
    en = (lang or "es")[:2] == "en"
    iv = int(rep.get("interval") or 1)
    f = rep.get("freq")
    if f == "weekly":
        names = [_WD["en" if en else "es"][d] for d in rep.get("days") or []]
        who = (", ".join(names[:-1]) + (" and " if en else " y ") + names[-1]) if len(names) > 1 else (
            names[0] if names else "")
        s = (f"every {who}" if iv == 1 else f"every {iv} weeks on {who}") if en else (
            (f"todos los {who}" if iv == 1 else f"cada {iv} semanas, los {who}"))
    elif f == "daily":
        s = ("every day" if iv == 1 else f"every {iv} days") if en else (
            "todos los días" if iv == 1 else f"cada {iv} días")
    else:
        s = ("every month" if iv == 1 else f"every {iv} months") if en else (
            "todos los meses" if iv == 1 else f"cada {iv} meses")
    if rep.get("until"):
        s += (f" until {rep['until']}" if en else f" hasta el {rep['until']}")
    else:
        s += " (no end date)" if en else " (sin fecha de fin)"
    if rep.get("skip"):
        # WHICH days, not how many (V2-770): with «1 día anulado» on the page the model answered «el martes 6
        # no hay clase» with «ese día ya está anulado» — the cancelled one was the 29th — and wrote nothing.
        days = ", ".join(sorted(rep["skip"])[:6]) + ("…" if len(rep["skip"]) > 6 else "")
        s += f", except {days}" if en else f", salvo {days} (anulados)"
    return s


def to_rrule(rep: dict) -> str:
    """The rule as Google Calendar's RRULE — the same series, not fifty-two single events."""
    if not isinstance(rep, dict):
        return ""
    parts = [f"FREQ={str(rep.get('freq') or 'weekly').upper()}"]
    if int(rep.get("interval") or 1) > 1:
        parts.append(f"INTERVAL={int(rep['interval'])}")
    if rep.get("freq") == "weekly" and rep.get("days"):
        parts.append("BYDAY=" + ",".join(("MO", "TU", "WE", "TH", "FR", "SA", "SU")[d] for d in rep["days"]))
    if rep.get("until"):
        parts.append("UNTIL=" + rep["until"].replace("-", "") + "T235959Z")
    return "RRULE:" + ";".join(parts)


# ── what the agenda's writes call (kept here: `data.py` sits at its line ceiling) ──────────────────────────

#: Every key `add_meeting`/`update_meeting` understand. Anything else a write carries is REPORTED back, never
#: dropped in silence — the dropped `recurrence` is how his Tuesdays vanished while the reply promised them.
MEETING_KEYS = frozenset(("title", "date", "startTime", "time", "endTime", "notes", "details", "location",
                          "place", "category", "attendees", "people", "with", "status", "confirmed", "allDay",
                          "all_day", "meet", "newTitle", "id", "item", "widget_id", "action") + ALL_KEYS)


def ignored_keys(payload: dict) -> list[str]:
    """The keys of a write that carried a value and that nothing here reads."""
    return [k for k, v in (payload or {}).items()
            if k not in MEETING_KEYS and not str(k).startswith("_") and v not in (None, "", [], {}, False)]


def attach(new: dict, payload: dict, today: str) -> str:
    """Give a NEW meeting its rule, if the write carries one. Returns why it could not ("" when fine).
    The row's `date` becomes the first day the rule lands on, so «los martes» said on a Friday starts on a
    Tuesday."""
    rep, why = parse(payload, str(new.get("date") or today), _date(today))
    if why:
        return why
    if rep:
        new["date"] = first_on_or_after(rep, str(new.get("date") or today))
        new["repeat"] = rep
    return ""


def update(m: dict, payload: dict, today: str) -> str:
    """Change the rule of an EXISTING meeting: set it, replace it, move only its end («hasta diciembre»), or
    drop it («ya no se repite»). Returns why it could not ("" when fine or when nothing about it was said)."""
    if not any(k in (payload or {}) for k in ALL_KEYS):
        return ""
    raw = next((payload[k] for k in RULE_KEYS if k in payload), None)
    if raw is False or (isinstance(raw, str) and _fold(raw) in _NONE_WORDS):
        m.pop("repeat", None)
        return ""
    cur = m.get("repeat") if isinstance(m.get("repeat"), dict) else None
    if cur and raw is None and not any(payload.get(k) for k in DAYS_KEYS):
        until, ok = parse_until(next((payload[k] for k in UNTIL_KEYS if payload.get(k)), ""), _date(today))
        if not ok:
            return "no entiendo hasta cuándo se repite — manda `until` como YYYY-MM-DD"
        cur["until"] = until
        return ""
    rep, why = parse(payload, str(m.get("date") or today), _date(today))
    if why:
        return why
    if rep:
        if cur and cur.get("skip"):
            rep["skip"] = cur["skip"]
        m["date"] = first_on_or_after(rep, str(m.get("date") or today))
        m["repeat"] = rep
    return ""


def weekday(date: str) -> int:
    """Monday = 0, the convention every `days` list here uses."""
    d = _date(date)
    return d.weekday() if d else 0


def on(m: dict, date: str) -> bool:
    """Does this row name `date` — its own day, or one its rule lands on? The selector every edit shares."""
    return str(m.get("date") or "") == date or (isinstance(m.get("repeat"), dict) and occurs_on(m, date))


def skip(m: dict, date: str) -> bool:
    """Cancel ONE occurrence of a series. True when there was one on that day to cancel."""
    if not (isinstance(m.get("repeat"), dict) and occurs_on(m, date)):
        return False
    m["repeat"].setdefault("skip", [])
    if date not in m["repeat"]["skip"]:
        m["repeat"]["skip"] = sorted(m["repeat"]["skip"] + [date])
    return True


# ── the model's own names for the fields, before anything reads them ─────────────────────────────────────
# Measured in the live use case (2026-09-25, sandbox 20260925-125624): the model sees action NAMES, never their
# payload shapes (`widgets/brief.py`, on purpose — shapes cost tokens every turn), so it NAMES the fields
# itself. It got the end right (`endDate` → until) and the rest wrong for us: the series landed on the day it
# was said (a Friday), all-day, because `startDate`, `start` and `dayOfWeek` were keys nobody read. A natural
# alias must never cost the fact (the V2-341/V2-473 rule), so they are mapped HERE, once, for every write.
_HHMM = re.compile(r"^\s*\d{1,2}([:h.]\d{2})?\s*(h|am|pm)?\s*$", re.I)
_DATE_ALIASES = ("startDate", "start_date", "fromDate", "from_date", "from", "desde", "firstDate", "first_date",
                 "day", "dia")
_START_ALIASES = ("start", "startHour", "start_hour", "hour", "hora", "startAt", "horaInicio", "hora_inicio",
                  "start_time", "starttime")
_END_ALIASES = ("end", "endHour", "end_hour", "endAt", "horaFin", "hora_fin", "end_time", "endtime")
_DAYS_ALIASES = ("dayOfWeek", "day_of_week", "weekday", "byday", "dia_semana", "diaSemana")


def normalize(payload: dict) -> dict:
    """A copy of `payload` with the model's natural field names mapped onto the agenda's own — only where the
    canonical key is absent, so an explicit field always wins. `start`/`end` go to the HOUR when they look like
    one and to the DAY when they look like a date (`end` as a date is the END of a series)."""
    p = dict(payload or {})

    def _take(keys):
        for k in keys:
            if p.get(k) not in (None, "", []):
                return k, p.pop(k)
        return None, None
    for k in ("start", "end"):
        v = p.get(k)
        if isinstance(v, str) and _date(v) and not _HHMM.match(v):
            p.pop(k)
            p.setdefault("date" if k == "start" else "until", v)
    if not p.get("date"):
        k, v = _take(_DATE_ALIASES)
        if k:
            p["date"] = v
    if not (p.get("startTime") or p.get("time")):
        k, v = _take(_START_ALIASES)
        if k:
            p["startTime"] = v
    if not p.get("endTime"):
        k, v = _take(_END_ALIASES)
        if k:
            p["endTime"] = v
    if not any(p.get(k) for k in DAYS_KEYS):
        k, v = _take(_DAYS_ALIASES)
        if k:
            p["days"] = v
    return p
