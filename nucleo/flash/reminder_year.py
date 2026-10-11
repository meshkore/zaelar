"""nucleo/flash/reminder_year.py — the YEAR of a reminder is the one the conversation said, and a past day is said.

Measured on `find-a-future-release-and-remind-me__us` (2026-10-11 02:27, today 2026-10-11): the search answered
«premieres on September 30th, 2026», he asked «Oh nice, September 30th. Could you remind me on premiere day?», and
the job was scheduled for 2027-09-30 09:00. `scheduler.parse_when` read his yearless «September 30th», saw it had
gone by and rolled it to next year — right when nobody said a year, wrong when the conversation did. The agenda
row said 2026-09-30; the notice rang a year late, about a day that had already happened.

The rule, for every reader of a reminder's moment:
  · `anchored` — a resolved day whose month-day the conversation named WITH a year takes that year;
  · `passed` — a day that is already behind us schedules nothing (`scheduler.parse_schedule` refuses it too), and
    `passed_line` is what the reply owes instead: that date has gone by, so nothing was set.
"""
from __future__ import annotations

import logging
import time as _time

from nucleo import scheduler as _sched

logger = logging.getLogger(__name__)


def _texts(reply: str, operator_text: str, window) -> list[str]:
    said = [str((m or {}).get("content") or "") for m in (window or [])]
    return [reply or "", operator_text or "", *reversed(said)]


def mention_for(when: str, reply: str = "", operator_text: str = "", window=None) -> tuple[str, str]:
    """The most recent «day month YEAR» the conversation said for `when`'s month-day → (iso date, as said)."""
    md = (when or "")[5:10]
    if not md:
        return "", ""
    for text in _texts(reply, operator_text, window):
        for iso, said in reversed(_sched.dated_mentions(text)):
            if iso[5:10] == md:
                return iso, said
    return "", ""


def anchored(when: str, reply: str = "", operator_text: str = "", window=None) -> str:
    """`when` with the year the conversation said for that day, if it said one; otherwise `when` unchanged."""
    iso, _ = mention_for(when, reply, operator_text, window)
    return f"{iso}{when[10:]}" if iso and iso != when[:10] else when


def passed(when: str, now: float | None = None) -> bool:
    """Is the DAY of `when` already behind us? (Today still counts: a 09:00 gone by is `reminder_before`'s job.)"""
    if not (when or "")[:10]:
        return False
    today = _time.strftime("%Y-%m-%d", _time.localtime(_time.time() if now is None else now))
    return when[:10] < today


def passed_line(when: str, reply: str = "", operator_text: str = "", window=None, lang_code: str = "") -> str:
    """What a reply that promised a notice for a day already gone by owes, in the session language — or ""."""
    if not passed(when):
        return ""
    _, said = mention_for(when, reply, operator_text, window)
    try:
        from i18n import langs as _lg
        return _lg.spec(lang_code or None).reminder_date_passed.format(date=said or when[:10])
    except Exception as e:  # noqa: BLE001
        logger.warning("past reminder date has no language line: %s", e)
        return ""
