"""nucleo/pulse/scheduler_when.py — a SPOKEN time expression → the ISO spec `parse_schedule` accepts (V2-146).

The backstop uses this when the model promised a reminder and emitted no tag; the model itself still writes ISO.
Arithmetic, not guesswork: "" as soon as the expression is ambiguous — a misdated reminder is only noticed the
day it fails to ring (V2-121). Tables and regexes live in `scheduler` (`_m`).
"""
from __future__ import annotations

import re

from nucleo.pulse import scheduler as _m


def _day_and_month(n: str, hh: int, mi: int, now: float) -> str | None:
    """«30 de octubre» / «October 30[, 2026]» → its spec; "" when said but impossible; None when not said (V2-781).
    It wins over a weekday beside it: «el viernes 30 de octubre» is the 30th, never the next Friday."""
    m = _m._RE_DAY_MONTH.search(n)
    day, mon, year = (int(m.group(1)), _m._MONTHS[m.group(2)], m.group(3)) if m else (0, 0, None)
    if not m and (m2 := _m._RE_MONTH_DAY.search(n)):
        day, mon, year = int(m2.group(2)), _m._MONTHS[m2.group(1)], m2.group(3)
    if not mon:
        return None
    lt = _m.time.localtime(now)
    for y in ([int(year)] if year else [lt.tm_year, lt.tm_year + 1]):
        try:
            ts = _m.time.mktime((y, mon, day, hh, mi, 0, 0, 1, -1))
        except (OverflowError, ValueError):
            return ""
        if _m.time.localtime(ts).tm_mday == day and (year or ts > now):
            return _m.time.strftime("%Y-%m-%d %H:%M", _m.time.localtime(ts))
    return ""


def dated_mentions(text: str) -> list[tuple[str, str]]:
    """Every day-and-month WITH a year in `text` → `[("YYYY-MM-DD", as said)]`, in order (2026-10-11).

    `parse_when` rolls a past yearless date to next year; a reader with the conversation uses this to keep a
    year that WAS said."""
    n = _m._strip_accents_sched(text)
    raw = text if len(text or "") == len(n) else n          # the words as said, when positions line up
    out = []
    for rx, d, mo in ((_m._RE_DAY_MONTH, 1, 2), (_m._RE_MONTH_DAY, 2, 1)):
        for m in rx.finditer(n):
            if m.group(3):
                try:
                    ts = _m.time.mktime((int(m.group(3)), _m._MONTHS[m.group(mo)], int(m.group(d)), 12, 0, 0, 0, 1, -1))
                except (OverflowError, ValueError):
                    continue
                if _m.time.localtime(ts).tm_mday == int(m.group(d)):
                    out.append((m.start(), _m.time.strftime("%Y-%m-%d", _m.time.localtime(ts)), raw[m.start():m.end()]))
    return [(iso, said) for _, iso, said in sorted(out)]


def _strip_accents_sched(text: str) -> str:
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()


def parse_when(text: str, now: float | None = None) -> str:
    """A spoken time expression → the `YYYY-MM-DD [HH:MM]` spec `parse_schedule` accepts, or "" if uncertain.

    Only unambiguous forms: tomorrow, a named weekday, a day of the month, each with an optional «a las HH(:MM)».
    «esta tarde», «pronto» or «cuando puedas» return "" on purpose — a guessed date is worse than none.
    """
    now = _m.time.time() if now is None else now
    n = _m._strip_accents_sched(text)
    if not n.strip():
        return ""
    m = _m._RE_AT_HOUR.search(n)
    hh, mi = _m._DEFAULT_HOUR, 0
    if m:
        hh = int(m.group(1) or m.group(3) or _m._DEFAULT_HOUR)
        mi = int(m.group(2) or m.group(4) or 0)
        if not (0 <= hh <= 23 and 0 <= mi <= 59):
            return ""

    def _iso(ts: float) -> str:
        return _m.time.strftime("%Y-%m-%d", _m.time.localtime(ts)) + f" {hh:02d}:{mi:02d}"

    def _at(day_ts: float) -> float:
        lt = _m.time.localtime(day_ts)
        return _m.time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mi, 0, 0, 1, -1))

    # «mañana» is both *tomorrow* and *morning* (V2-151: «el miércoles a media mañana» resolved to THURSDAY).
    # The noun always carries a determiner; drop those first and only the adverb is left.
    if re.search(r"\b(manana|tomorrow)\b", _m._RE_MORNING_NOUN.sub(" ", n)):
        return _iso(now + 86400)
    if (dm := _m._day_and_month(n, hh, mi, now)) is not None:
        return dm
    # TWO weekdays in one sentence is ambiguous for a backstop: "" hands it back to whoever has the context.
    found = {t for name, t in _m._WEEKDAYS.items() if re.search(rf"\b{name}\b", n)}
    if len(found) > 1:
        return ""
    if found:
        target = found.pop()
        today = _m.time.localtime(now).tm_wday
        delta = (target - today) % 7
        if delta == 0 and _at(now) <= now:          # today, but the hour already went by → next week
            delta = 7
        return _iso(now + delta * 86400)
    m = _m._RE_DAY_OF_MONTH.search(n)
    if m:
        day = int(m.group(1) or m.group(2))
        if not (1 <= day <= 31):
            return ""
        lt = _m.time.localtime(now)
        for month_offset in (0, 1):
            year, month = lt.tm_year + (lt.tm_mon + month_offset - 1) // 12, (lt.tm_mon + month_offset - 1) % 12 + 1
            try:
                ts = _m.time.mktime((year, month, day, hh, mi, 0, 0, 1, -1))
            except (OverflowError, ValueError):
                return ""
            if ts > now and _m.time.localtime(ts).tm_mday == day:
                return _m.time.strftime("%Y-%m-%d %H:%M", _m.time.localtime(ts))
        return ""
    return ""
