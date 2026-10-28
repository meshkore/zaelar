"""nucleo/pulse/scheduler_cron.py — a `schedule` spec → its next run: relative, ISO date, interval, 5-field cron.

Regexes and bounds live in `scheduler` (`_m`).
"""
from __future__ import annotations

from nucleo.pulse import scheduler as _m


def parse_schedule(spec: str, now: float | None = None) -> dict | None:
    """Return a normalized schedule dict (with `next_run` in epoch time), or None if unrecognized."""
    now = _m.time.time() if now is None else now
    s = (spec or "").strip()
    if not s:
        return None
    m = _m._RE_EVERY.match(s)
    if m:
        iv = int(m.group(1)) * _m._UNIT_S[m.group(2).lower()]
        if iv <= 0:
            return None
        return {"type": "interval", "interval_s": iv, "next_run": int(now + iv),
                "display": f"cada {m.group(1)}{m.group(2).lower()}"}
    m = _m._RE_ONCE.match(s)
    if m:
        iv = int(m.group(1)) * _m._UNIT_S[m.group(2).lower()]
        if iv <= 0:
            return None
        return {"type": "once", "interval_s": iv, "next_run": int(now + iv),
                "display": f"en {m.group(1)}{m.group(2).lower()}"}
    m = _m._RE_ABS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4)) if m.group(4) is not None else _m._DEFAULT_HOUR
        mi = int(m.group(5)) if m.group(5) is not None else 0
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 23 and 0 <= mi <= 59):
            return None
        try:
            # mktime reads the tuple in LOCAL time (the operator's zone), as `next_cron` does.
            ts = _m.time.mktime((y, mo, d, hh, mi, 0, 0, 1, -1))
        except (OverflowError, ValueError):
            return None
        # A PAST date is refused: the operator would believe it was set for the next occurrence.
        if ts <= now:
            return None
        return {"type": "once", "interval_s": int(ts - now), "next_run": int(ts),
                "display": _m.time.strftime("%Y-%m-%d %H:%M", _m.time.localtime(ts))}
    if len(s.split()) == 5:
        nr = _m.next_cron(s, now)
        if nr is not None:
            return {"type": "cron", "cron": s, "next_run": int(nr), "display": s}
    return None


def _advance(sch: dict, fired_at: float) -> dict | None:
    """Recalculate `next_run` after a trigger. `once` → None (it closes). Recurring → next occurrence."""
    t = sch.get("type")
    if t == "once":
        return None
    if t == "interval":
        sch = dict(sch)
        sch["next_run"] = int(fired_at + sch["interval_s"])
        return sch
    if t == "cron":
        nr = _m.next_cron(sch["cron"], fired_at)
        if nr is None:
            return None
        sch = dict(sch)
        sch["next_run"] = int(nr)
        return sch
    return None


def _parse_field(field: str, lo: int, hi: int) -> set[int] | None:
    """Expand a cron field into a set of allowed values. None if invalid."""
    out: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            return None
        step = 1
        if "/" in part:
            base, _, st = part.partition("/")
            if not st.isdigit() or int(st) <= 0:
                return None
            step = int(st)
            part = base
        if part in ("*", ""):
            a, b = lo, hi
        elif "-" in part:
            aa, _, bb = part.partition("-")
            if not (aa.isdigit() and bb.isdigit()):
                return None
            a, b = int(aa), int(bb)
        elif part.isdigit():
            a = b = int(part)
        else:
            return None
        if a < lo or b > hi or a > b:
            return None
        out.update(range(a, b + 1, step))
    return out or None


def _cron_fields(expr: str):
    parts = expr.split()
    if len(parts) != 5:
        return None
    fields = []
    for raw, (lo, hi) in zip(parts, _m._FIELD_BOUNDS):
        f = _m._parse_field(raw, lo, hi)
        if f is None:
            return None
        restricted = raw.strip() != "*" and not raw.strip().startswith("*/")   # not a full wildcard
        fields.append((f, restricted, raw.strip()))
    return fields


def next_cron(expr: str, after: float) -> float | None:
    """Next minute-aligned epoch (>= after+60s) matching `expr`; None if invalid or nothing in ~1 year.
    Bounded minute-by-minute search."""
    fields = _m._cron_fields(expr)
    if fields is None:
        return None
    (mins, _, _), (hours, _, _), (doms, dom_r, _), (months, _, _), (dows, dow_r, _) = fields
    t = (int(after) // 60 + 1) * 60
    cap = t + 366 * 86400
    while t <= cap:
        lt = _m.time.localtime(t)
        # Standard cron: with dom AND dow both restricted, EITHER matching is enough.
        dow0 = lt.tm_wday  # Monday=0..Sunday=6
        cron_dow = (dow0 + 1) % 7  # cron: Sunday=0..Saturday=6
        dom_ok = lt.tm_mday in doms
        dow_ok = cron_dow in dows
        day_ok = (dom_ok or dow_ok) if (dom_r and dow_r) else (dom_ok and dow_ok)
        if lt.tm_min in mins and lt.tm_hour in hours and lt.tm_mon in months and day_ok:
            return float(t)
        t += 60
    return None
