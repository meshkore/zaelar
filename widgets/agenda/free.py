"""Free time on a day — the QUESTION «find me a free 45 minutes tomorrow afternoon» answered, nothing written.

Demo passes 2026-09-28 (C2, three passes running): the question booked the meeting. `add_meeting`'s description
said in so many words that finding a slot is a question, and it did not matter: the agenda had no action that
FINDS time, so the model reached for the nearest one it had, which writes. An undeclared capability is not one the
model can decline. This is that capability: the free stretches of a day, inside a window, at least as long as asked.
Stdlib only; the day's appointments come from the same store and the same day test the reader uses."""
from __future__ import annotations

_DAY_START, _DAY_END = "08:00", "20:00"
_MAX_SLOTS = 5
#: A part of the day said as a WORD in a window field (demo pass 109, C2): `from: "afternoon"` fell to 08:00 and the
#: first slot was the morning. Product vocabulary (es/en), the windows the manifest already describes.
_PARTS = {"morning": ("08:00", "12:00"), "mañana": ("08:00", "12:00"), "manana": ("08:00", "12:00"),
          "noon": ("12:00", "15:00"), "midday": ("12:00", "15:00"), "mediodia": ("12:00", "15:00"),
          "mediodía": ("12:00", "15:00"), "afternoon": ("12:00", "20:00"), "tarde": ("12:00", "20:00"),
          "evening": ("18:00", "22:00"), "night": ("18:00", "22:00"), "noche": ("18:00", "22:00")}
#: How long a slot this card FOUND stays the hour of a booking that names none («ok book it»).
FRESH_S = 30 * 60


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


def _first_time(payload: dict, keys: tuple) -> int | None:
    vals = [_m(payload.get(k)) for k in keys]      # «00:00» is a time: `or` read midnight as «no time»
    return next((v for v in vals if v is not None), None)


#: Where a part of the day may arrive — pass 111, C2: the model wrote `period`, and the window was the whole day.
_PART_KEYS = ("from", "after", "start", "window", "part", "period", "part_of_day", "time_of_day", "to", "before", "end")


def _window(payload: dict) -> tuple[int, int]:
    part = next((_PARTS[w] for k in _PART_KEYS
                 if (w := str(payload.get(k) or "").strip().lower()) in _PARTS), (_DAY_START, _DAY_END))
    lo, hi = _first_time(payload, ("from", "after", "start")), _first_time(payload, ("to", "before", "end"))
    return (_m(part[0]) if lo is None else lo), (_m(part[1]) if hi is None else hi)


def _yes(v) -> bool:
    return v is True or str(v or "").strip().lower() in ("true", "1", "yes", "si", "sí")


def find(meetings: list, day: str, payload: dict) -> dict:
    need = _minutes(payload)
    lo, hi = _window(payload)
    taken = busy(meetings, day)
    if _yes(payload.get("after_last")) and taken:
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


def remember(db: dict, res: dict, payload: dict) -> dict:
    """Keep the first slot found, so «ok book it» books THAT (demo pass 109, C3: it lived only in the reply, the
    reply went wrong, and the booking invented 11:45 beside a 15:00 the card knew about). Returns `res`."""
    import time as _t
    first = ((res or {}).get("free") or [{}])[0].get("first_fit") or ""
    if "-" in first:
        a, b = first.split("-", 1)
        db["proposed"] = {"date": res["date"], "startTime": a, "endTime": b, "minutes": res.get("minutes"),
                          "at": _t.time()}
    return res


def with_the_slot_found(db: dict, payload: dict, resolve_date) -> dict:
    """A booking that names no hour, right after this card found a slot (same day, or none said), takes that slot
    — and spends it: a later booking with no hour is a new question, not the same slot twice."""
    import time as _t
    p = db.get("proposed") or {}
    if not p or any(str(payload.get(k) or "").strip() for k in ("startTime", "time", "start", "allDay")):
        return payload
    if _t.time() - float(p.get("at") or 0) > FRESH_S:
        return payload
    said = str(payload.get("date") or "").strip()
    if said and str(resolve_date(said)) != str(p.get("date")):
        return payload
    db.pop("proposed", None)
    return {**payload, "date": p["date"], "startTime": p["startTime"],
            "endTime": str(payload.get("endTime") or "") or p["endTime"]}


def clashes(meetings: list, row: dict | None) -> list[dict]:
    """Timed appointments a just-written row overlaps that day — said back, never refused: he may mean it."""
    if not isinstance(row, dict) or row.get("allDay"):
        return []
    s, e = _m(row.get("startTime")), _m(row.get("endTime"))
    if s is None:
        return []
    e = e if e and e > s else s + 30
    return [{"title": t, "from": _hhmm(a), "to": _hhmm(b)} for a, b, t in busy(meetings, str(row.get("date") or ""))
            if a < e and s < b and t != str(row.get("title") or "")]


_MAX_SPAN_DAYS = 62


def span_end(meetings: list, day: str, payload: dict) -> str:
    """The last day a search asked BY ITS LENGTH covers, or "" — pass 115, R3: «five days in her vacation» came as
    {date, duration_min: 7200} with the stretch only in words, and one day was searched. A length of a day or more
    with no `until` is a stretch: the all-day span that covers `day` ends it, else the days the length adds up to."""
    import datetime as _dt
    need = 0
    for k in ("duration_min", "minutes", "duration", "length"):
        try:
            need = need or int(float(str(payload.get(k)).strip()))
        except (TypeError, ValueError):
            pass                          # `_minutes` caps a slot at 12 h: a stretch is read uncapped
    if need < 24 * 60:
        return ""
    try:
        d0 = _dt.date.fromisoformat(str(day)[:10])
    except ValueError:
        return ""
    for m in meetings or []:
        rep = m.get("repeat") if isinstance(m.get("repeat"), dict) else {}
        if (m.get("allDay") and rep.get("freq") == "daily" and int(rep.get("interval") or 1) == 1
                and str(m.get("date") or "") <= str(d0) <= str(rep.get("until") or "")):
            return str(rep["until"])
    return (d0 + _dt.timedelta(days=-(-need // (24 * 60)) - 1)).isoformat()


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

