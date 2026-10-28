"""nucleo/flash/notice_readback.py — a notice that was MOVED to ring soon today is said at the time it rings.

Measured on `remember-and-remind-deadline` (Wednesday 2026-10-14, noon): the reply said «te aviso el miércoles 14 a
las 9» — an instant already gone — while the job went in for another moment altogether. Reply and job have to
agree, and the job is the one that rings: so the time said is READ BACK from the live schedule, never recomputed.

`nucleo.notice_today` notes every move it makes (the agenda's notice and the model's tag both go through it); this
reads the turn's latest move, checks a live job really rings at that instant, and returns the sentence the reply
owes — "" when nothing moved, the job is not there, or the reply already says that hour.
"""
from __future__ import annotations

import logging
import re
import time

from nucleo import notice_today as _nt
from nucleo.pulse import scheduler as _sched

logger = logging.getLogger(__name__)


def _says_hour(spoken: str, hhmm: str) -> bool:
    h, m = int(hhmm[:2]), hhmm[3:5]
    h12 = h % 12 or 12
    pats = [rf"\b{h}[:.h]{m}\b", rf"\b{h:02d}[:.h]{m}\b"]
    if m == "00":
        pats += [rf"\b{h12}\s*(?:[ap]\.?m\b|o'?clock)", rf"\blas\s+{h}\b(?![:.]\d)"]
    return any(re.search(p, spoken or "", re.I) for p in pats)


def moved_line(spoken: str, lang_code: str = "", now: float | None = None) -> str:
    """The sentence the reply owes for a notice moved this turn to ring soon today, or ""."""
    mv = _nt.take_move(time.time() if now is None else now)
    if not mv:
        return ""
    try:
        live = any(str(j.get("schedule") or "") == mv["at"] for j in _sched.list_jobs(active_only=True))
    except Exception as e:  # noqa: BLE001 — the schedule could not be read: nothing can be read back
        logger.warning("moved notice not read back, scheduled_jobs unreadable: %s", e)
        return ""
    at = mv["at"][11:16]
    if not live or _says_hour(spoken, at):
        return ""
    try:
        from i18n import langs as _lg
        return _lg.spec(lang_code or None).reminder_moved_soon.format(asked=mv["asked"][11:16], at=at)
    except Exception as e:  # noqa: BLE001
        logger.warning("moved notice has no language line: %s", e)
        return ""
