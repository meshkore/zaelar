"""widgets/agenda/title_when.py — an appointment's TITLE says what it is, never when (agenda-appointment-lifecycle).

Measured 2026-10-10 (use case `agenda-appointment-lifecycle`, ES): the dated-note backstop built its title out of
his whole sentence and the row read «una revision del coche en el taller el 20 de octubre a las diez de la». The
appointment was later moved to 17:00 and the title still said ten in the morning: the WHEN lives in `date` and
`startTime`, and a copy of it in the title goes stale the first time the appointment moves.

Only COMPLETE date and time expressions are cut — a lead word («el», «a las», «on», «at») plus a day/month or an
hour — so a title that merely carries a number («Clase 3 de piano», «Room 101», «Revisión de los 10.000 km»,
«Meeting at 10 Downing Street») keeps it. A time phrase is cut only when its hour can be READ, and the hour is
handed back so the caller can store it: the title is never the place an hour is lost from. Stdlib only.
"""
from __future__ import annotations

import re

_MONTHS_ES = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
_MONTHS_EN = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
              r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_DAYS_ES = r"(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)"
_DAYS_EN = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
_WORDS_ES = ("una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once", "doce")
_WORDS_EN = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve")
_HOUR_WORDS = {**{w: i + 1 for i, w in enumerate(_WORDS_ES)}, **{w: i + 1 for i, w in enumerate(_WORDS_EN)},
               "noon": 12, "midnight": 0}
# What may follow a time phrase: the end, punctuation, or the next WHEN word. Without it «at 10 Downing Street»
# would lose its number.
_END = r"(?=\s*(?:$|[,.;:)]|\b(?:el|on|this|next|tomorrow|today|hoy|ma[ñn]ana|para)\b))"

_DATE_CUTS = (
    # ES: «el 20 de octubre», «para el martes 20 de octubre de 2026», «el día 20 de octubre»
    re.compile(r"\s*,?\s*\b(?:para\s+el|el|d[ií]a)\s+(?:" + _DAYS_ES + r"\s+)?(?:d[ií]a\s+)?\d{1,2}\s+de\s+"
               + _MONTHS_ES + r"(?:\s+(?:de|del)\s+\d{4})?\b", re.I),
    # EN: «on October 20», «on Tuesday, October 20th, 2026», «on the 20th of October»
    re.compile(r"\s*,?\s*\bon\s+(?:" + _DAYS_EN + r",?\s+)?(?:" + _MONTHS_EN + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?"
               r"|(?:the\s+)?\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MONTHS_EN + r")(?:,?\s+\d{4})?\b", re.I),
)
_TIME_CUTS = (
    # ES: «a las diez de la mañana», «a las 17:00», «a las cinco y media de la tarde», and the truncated «a las
    # diez de la» the backstop's own date cut leaves behind (it reads «mañana» as tomorrow).
    re.compile(r"\s*,?\s*\b(?:a|sobre|hacia)\s+las?\s+(?P<h>\d{1,2}(?:[:.h]\d{2})?|" + "|".join(_WORDS_ES) + r")"
               r"(?P<m>\s+y\s+(?:media|cuarto|\d{1,2}))?"
               r"(?P<p>\s+(?:de\s+la\s+(?:ma[ñn]ana|tarde|noche|madrugada)|del\s+mediod[ií]a|de\s+la|en\s+punto|"
               r"h|horas))?" + _END, re.I),
    # EN: «at ten in the morning», «at 5pm», «at 17:00», «at five o'clock»
    re.compile(r"\s*,?\s*\bat\s+(?P<h>\d{1,2}(?::\d{2})?|" + "|".join(_WORDS_EN) + r"|noon|midnight)"
               r"(?P<m>)(?P<p>\s*(?:a\.?m\.?|p\.?m\.?)|\s+(?:o'?clock|in\s+the\s+(?:morning|afternoon|evening)|"
               r"at\s+night|tonight|sharp))?" + _END, re.I),
)
_LEAD_ARTICLE = re.compile(r"^(?:un|una|a|an)\s+", re.I)


def _hour_of(m: re.Match) -> str:
    """'HH:MM' for a matched time phrase, "" when it cannot be read with certainty (then it is not cut)."""
    h_raw = m.group("h").strip().lower()
    part = (m.group("p") or "").lower()
    extra = (m.group("m") or "").lower()
    num = re.match(r"(\d{1,2})(?:[:.h](\d{2}))?$", h_raw)
    if num:
        h, mins = int(num.group(1)), int(num.group(2) or 0)
    elif h_raw in _HOUR_WORDS:
        h, mins = _HOUR_WORDS[h_raw], 0
    else:
        return ""
    if "media" in extra:
        mins = 30
    elif "cuarto" in extra:
        mins = 15
    elif (em := re.search(r"\d{1,2}", extra)):
        mins = int(em.group())
    pm = re.search(r"tarde|noche|p\.?m|afternoon|evening|night", part) is not None
    am = re.search(r"ma[ñn]ana|madrugada|a\.?m|morning|de\s+la$", part.strip()) is not None   # «de la» = «de la mañana» cut
    explicit_24h = bool(num and num.group(2)) or h > 12
    if pm and h < 12:
        h += 12
    elif not am and not explicit_24h and 1 <= h <= 7 and h_raw not in ("noon", "midnight"):
        h += 12                                       # the agenda's own rule for a bare 1-7 (`when._resolve_time`)
    if not (0 <= h <= 23 and 0 <= mins <= 59):
        return ""
    return f"{h:02d}:{mins:02d}"


def split_when(title: str, *, date: bool = True) -> tuple[str, str]:
    """`(title without its date/time phrases, 'HH:MM' the cut time phrase said, or "")`. Never raises.

    A time phrase whose hour cannot be read is LEFT in the title; so is everything when cutting would leave fewer
    than three characters to name the appointment."""
    raw = str(title or "").strip()
    out, hour = raw, ""
    if date:
        for rx in _DATE_CUTS:
            out = rx.sub("", out)
    for rx in _TIME_CUTS:
        m = rx.search(out)
        h = _hour_of(m) if m else ""
        if h:
            hour = hour or h
            out = out[:m.start()] + out[m.end():]
    out = re.sub(r"\s{2,}", " ", _LEAD_ARTICLE.sub("", out.strip(" ,.;:"))).strip(" ,.;:")
    if out == raw:
        return raw, hour
    if len(out) < 3:
        return raw, ""
    return out[:1].upper() + out[1:], hour


def strip_when(title: str) -> str:
    """`title` without the date and time phrases it carries (see `split_when`)."""
    return split_when(title)[0]
