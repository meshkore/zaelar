"""Free time on a day — the QUESTION «find me a free 45 minutes tomorrow afternoon» answered, nothing written.

Demo passes 2026-09-28 (C2, three passes running): the question booked the meeting. `add_meeting`'s description
said in so many words that finding a slot is a question, and it did not matter: the agenda had no action that
FINDS time, so the model reached for the nearest one it had, which writes. An undeclared capability is not one the
model can decline. This is that capability: the free stretches of a day, inside a window, at least as long as asked.
Stdlib only; the day's appointments come from the same store and the same day test the reader uses."""
from __future__ import annotations

_DAY_START, _DAY_END = "08:00", "20:00"
_MAX_SLOTS = 5


def _m(hhmm) -> int | None:
    try:
        h, mm = str(hhmm or "").strip().split(":")[:2]
        v = int(h) * 60 + int(mm)
        return v if 0 <= v <= 24 * 60 else None
    except Exception:  # noqa: BLE001
        return None


def _hhmm(v: int) -> str:
    return f"{v // 60:02d}:{v % 60:02d}"


def _minutes(payload: dict) -> int:
    for k in ("duration_min", "minutes", "duration", "length"):
        raw = payload.get(k)
        try:
            v = int(float(str(raw).strip())) if raw not in (None, "") else 0
        except (TypeError, ValueError):
            v = _m(raw) or 0                       # «00:45»
        if v > 0:
            return min(v, 12 * 60)
    return 30


def busy(meetings: list, day: str) -> list[tuple[int, int, str]]:
    """(start, end, title) of every timed appointment that day, sorted. An all-day one blocks nothing by the clock."""
    from .query import _on_day
    out = []
    for mt in meetings or []:
        if not isinstance(mt, dict) or mt.get("allDay") or not _on_day(mt, day):
            continue
        s = _m(mt.get("startTime") or mt.get("start") or mt.get("time"))
        if s is None:
            continue
        e = _m(mt.get("endTime") or mt.get("end"))
        out.append((s, e if e and e > s else s + 30, str(mt.get("title") or "")))
    return sorted(out)


def find(meetings: list, day: str, payload: dict) -> dict:
    need = _minutes(payload)
    lo = _m(payload.get("from") or payload.get("after") or payload.get("start")) or _m(_DAY_START)
    hi = _m(payload.get("to") or payload.get("before") or payload.get("end")) or _m(_DAY_END)
    taken = busy(meetings, day)
    if payload.get("after_last") and taken:
        lo = max(lo, max(e for _s, e, _t in taken))
    slots, cur = [], lo
    for s, e, _t in taken:
        if s > cur and min(s, hi) - cur >= need:
            slots.append((cur, min(s, hi)))
        cur = max(cur, e)
    if hi - cur >= need:
        slots.append((cur, hi))
    return {"ok": True, "date": day, "minutes": need, "window": [_hhmm(lo), _hhmm(hi)],
            "free": [{"from": _hhmm(a), "to": _hhmm(b), "first_fit": f"{_hhmm(a)}-{_hhmm(a + need)}"}
                     for a, b in slots[:_MAX_SLOTS]],
            "busy": [{"from": _hhmm(s), "to": _hhmm(e), "title": t} for s, e, t in taken],
            "booked": False,
            "note": "nothing was booked — say the free time and wait for him to ask to book it (add_meeting)"}


_MAX_SPAN_DAYS = 62


def find_span(meetings: list, first: str, last: str, payload: dict) -> dict:
    """Across days («five days in her vacation where I'm free»): which days in [first, last] have NO timed
    appointment — and, for the others, whether the slot asked for still fits. An all-day entry (her vacation
    itself) blocks nothing by the clock, as on one day."""
    import datetime as _dt
    try:
        d0, d1 = _dt.date.fromisoformat(first), _dt.date.fromisoformat(last)
    except ValueError:
        return {"ok": False, "error": "until must be a date (YYYY-MM-DD) on or after date"}
    if d1 < d0:
        d0, d1 = d1, d0
    days = [(d0 + _dt.timedelta(days=i)).isoformat() for i in range(min((d1 - d0).days + 1, _MAX_SPAN_DAYS))]
    free_days, busy_days = [], []
    for day in days:
        taken = busy(meetings, day)
        if not taken:
            free_days.append(day)
        else:
            fits = find(meetings, day, payload)["free"]
            busy_days.append({"date": day, "busy": [f"{_hhmm(s)}-{_hhmm(e)} {t}" for s, e, t in taken],
                              "still_fits": bool(fits)})
    return {"ok": True, "from": days[0], "until": days[-1], "free_days": free_days, "days_with_appointments": busy_days,
            "booked": False, "note": "nothing was booked — say the free days he asked for"}

