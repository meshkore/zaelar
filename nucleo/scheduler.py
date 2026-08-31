"""nucleo/scheduler.py — the brain v2's OWN cron (V2-005 · T71).

Replaces **Hermes's native cron** (`brains/hermes/cron.py`, which dies with Hermes in V2-009). Scheduled tasks
are **persisted in `memory.journal`** (continuity after restart) and triggered by the orchestrator loop
(`nucleo/loop.py`, ~1 Hz). There is no external process or binary: triggering and delivery live in OUR process.

`schedule` formats (the same ones shown by the cron brief; the parser is language-agnostic):
  - **one-time, relative**: `"30m"`, `"2h"`, `"1d"`, `"45s"` (also `"en 30m"`, `"in 2h"`, `"+1h"`).
  - **one-time, ABSOLUTE DATE**: `"2026-08-19 09:00"` (or `"2026-08-19T09:00"`, or `"2026-08-19"` → 09:00 by
    default). Added 2026-08-18 (V2-121): without this there was NO way to schedule a one-time reminder on a
    specific DAY — «recuérdamelo el miércoles» could only be expressed as a 5-field cron `0 9 * * 3`, which is
    RECURRING (alerts every Wednesday forever), or by counting days manually (`2d`), which is fragile and opaque.
    The `remember-and-remind-deadline` use case measured this: the reminder never came into existence.
  - **recurring by interval**: `"every 30m"`, `"cada 2h"`.
  - **cron 5-campos**: `"0 9 * * *"` (min hora dom mes dow; soporta `* , - /`).

The scheduler does NOT run an agent per task (Hermes did): it delivers the task's `prompt` through the proactive
rails (voice + UI), which is what a reminder needs. A task involving a condition/reasoning is escalated to
SlowBrain (V2-006/007); until then, the prompt is delivered as-is (self-contained reminder).
"""
from __future__ import annotations

import re
import time

from memory import journal as _journal

_KIND = "scheduled"

# Time units → seconds (language-agnostic parser).
_UNIT_S = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "day": 86400}

_RE_EVERY = re.compile(r"^(?:every|cada)\s+(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", re.I)
_RE_ONCE = re.compile(r"^(?:in\s+|en\s+|\+)?(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", re.I)
# ABSOLUTE one-time date (V2-121): ISO `YYYY-MM-DD` with an optional time separated by a space or `T`.
# Deliberately ISO ONLY: the brain prompt already contains today's and tomorrow's date in that same format
# (`prompt.live_state`), so the model does not have to invent a date grammar — it translates «el miércoles»
# to the date already in front of it. An ambiguous local format (19/08 vs 08/19) is intentionally rejected.
_RE_ABS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?$")
# Default hour when a day is given without a time: a «el miércoles» reminder is delivered in the morning.
_DEFAULT_HOUR = 9


# ── a SPOKEN time expression → the ISO date that `parse_schedule` already understands ──────────────────────
#
# V2-146 — «apúntame que el jueves… y recuérdamelo el miércoles» ended with `scheduled_jobs.created` EMPTY: the
# model promised the reminder in prose and emitted no tag. The cron executor works (verified in
# V2-134), the prompt explicitly requests it — what was missing was the backstop, and a backstop needs to
# resolve «el miércoles» ON ITS OWN.
#
# This does NOT contradict the decision above to accept only ISO in `parse_schedule`. That decision says the MODEL
# should not have to invent a date grammar when it has the list of days in front of it, and it still stands: this
# function is not used by the model; the backstop uses it when the model did nothing. And it is arithmetic, not
# guesswork: it returns "" as soon as the expression is not unambiguous, because a wrongly dated reminder is not noticed
# until the day it fails to sound (V2-121).
_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
# «mañana» as the NOUN *morning* — see `parse_when`. Always determined; the adverb *tomorrow* never is.
_RE_MORNING_NOUN = re.compile(r"\b(?:por\s+la|de\s+la|a\s+la|en\s+la|la|una|media|esta|toda\s+la)\s+manana\b", re.I)
_RE_AT_HOUR = re.compile(r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\b|\bat\s+(\d{1,2})(?::(\d{2}))?\b", re.I)
_RE_DAY_OF_MONTH = re.compile(r"\bel\s+d[ií]a\s+(\d{1,2})\b|\bon\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)


def _strip_accents_sched(text: str) -> str:
    import unicodedata as _ud
    return "".join(c for c in _ud.normalize("NFKD", text or "") if not _ud.combining(c)).lower()


def parse_when(text: str, now: float | None = None) -> str:
    """A spoken time expression → the `YYYY-MM-DD [HH:MM]` spec `parse_schedule` accepts, or "" if uncertain.

    Only the forms that are unambiguous on their own: tomorrow, a named weekday, and a day of the month, each
    with an optional «a las HH(:MM)». «esta tarde», «pronto» or «cuando puedas» return "" on purpose — a
    reminder placed on a guessed date is worse than none, because the operator believes it is set.
    """
    now = time.time() if now is None else now
    n = _strip_accents_sched(text)
    if not n.strip():
        return ""
    m = _RE_AT_HOUR.search(n)
    hh, mi = _DEFAULT_HOUR, 0
    if m:
        hh = int(m.group(1) or m.group(3) or _DEFAULT_HOUR)
        mi = int(m.group(2) or m.group(4) or 0)
        if not (0 <= hh <= 23 and 0 <= mi <= 59):
            return ""

    def _iso(ts: float) -> str:
        return time.strftime("%Y-%m-%d", time.localtime(ts)) + f" {hh:02d}:{mi:02d}"

    def _at(day_ts: float) -> float:
        lt = time.localtime(day_ts)
        return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mi, 0, 0, 1, -1))

    # «mañana» is TWO words in Spanish: the adverb *tomorrow* and the noun *morning*. Measured on the run where
    # V2-151 came from: «te programo un recordatorio para el miércoles a media mañana» resolved to THURSDAY,
    # because the noun inside «media mañana» matched the adverb and short-circuited the weekday below. That is
    # the worst failure this function can have — a reminder that is set, reported as set, and fires on the wrong
    # day, which nobody notices until the day it does not ring. The noun always carries a determiner in front
    # («la/media/esta/por la/de la mañana»); the bare adverb never does, so dropping the noun occurrences first
    # leaves exactly the adverb. «mañana por la mañana» still resolves to tomorrow: the first one survives.
    if re.search(r"\b(manana|tomorrow)\b", _RE_MORNING_NOUN.sub(" ", n)):
        return _iso(now + 86400)
    # TWO weekdays in the same sentence («el jueves tengo que… y recuérdamelo el miércoles») is ambiguous for a
    # backstop: which one is the reminder is exactly what we cannot know without understanding the sentence.
    # Answering "" sends it back to whoever has the context, instead of picking whichever the dict listed first.
    found = {t for name, t in _WEEKDAYS.items() if re.search(rf"\b{name}\b", n)}
    if len(found) > 1:
        return ""
    if found:
        target = found.pop()
        today = time.localtime(now).tm_wday
        delta = (target - today) % 7
        if delta == 0 and _at(now) <= now:          # today, but the hour already went by → next week
            delta = 7
        return _iso(now + delta * 86400)
    m = _RE_DAY_OF_MONTH.search(n)
    if m:
        day = int(m.group(1) or m.group(2))
        if not (1 <= day <= 31):
            return ""
        lt = time.localtime(now)
        for month_offset in (0, 1):
            year, month = lt.tm_year + (lt.tm_mon + month_offset - 1) // 12, (lt.tm_mon + month_offset - 1) % 12 + 1
            try:
                ts = time.mktime((year, month, day, hh, mi, 0, 0, 1, -1))
            except (OverflowError, ValueError):
                return ""
            if ts > now and time.localtime(ts).tm_mday == day:
                return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
        return ""
    return ""


    # ── schedule parsing ──────────────────────────────────────────────────────────────────────────────────
def parse_schedule(spec: str, now: float | None = None) -> dict | None:
    """Return a normalized schedule dict (with `next_run` in epoch time), or None if unrecognized."""
    now = time.time() if now is None else now
    s = (spec or "").strip()
    if not s:
        return None
    m = _RE_EVERY.match(s)
    if m:
        iv = int(m.group(1)) * _UNIT_S[m.group(2).lower()]
        if iv <= 0:
            return None
        return {"type": "interval", "interval_s": iv, "next_run": int(now + iv),
                "display": f"cada {m.group(1)}{m.group(2).lower()}"}
    m = _RE_ONCE.match(s)
    if m:
        iv = int(m.group(1)) * _UNIT_S[m.group(2).lower()]
        if iv <= 0:
            return None
        return {"type": "once", "interval_s": iv, "next_run": int(now + iv),
                "display": f"en {m.group(1)}{m.group(2).lower()}"}
    m = _RE_ABS.match(s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        hh = int(m.group(4)) if m.group(4) is not None else _DEFAULT_HOUR
        mi = int(m.group(5)) if m.group(5) is not None else 0
        if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= hh <= 23 and 0 <= mi <= 59):
            return None
        try:
            # mktime interprets the tuple in LOCAL TIME, which is the operator's time zone — just like `next_cron`.
            ts = time.mktime((y, mo, d, hh, mi, 0, 0, 1, -1))
        except (OverflowError, ValueError):
            return None
        # A date that has already PASSED is not scheduled: delivering «ya» a reminder for last Thursday is worse than rejecting it,
        # because the operator believes it was set for the next occurrence.
        if ts <= now:
            return None
        return {"type": "once", "interval_s": int(ts - now), "next_run": int(ts),
                "display": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))}
    if len(s.split()) == 5:
        nr = next_cron(s, now)
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
        nr = next_cron(sch["cron"], fired_at)
        if nr is None:
            return None
        sch = dict(sch)
        sch["next_run"] = int(nr)
        return sch
    return None


# ── 5-field cron (min hour dom month dow) ─────────────────────────────────────────────────────────────────
_FIELD_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]  # dow: 0=Sunday


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
    for raw, (lo, hi) in zip(parts, _FIELD_BOUNDS):
        f = _parse_field(raw, lo, hi)
        if f is None:
            return None
        # Was it restricted (was not a full wildcard)?
        restricted = raw.strip() != "*" and not raw.strip().startswith("*/")
        fields.append((f, restricted, raw.strip()))
    return fields


def next_cron(expr: str, after: float) -> float | None:
    """Next epoch (>= after+60s, aligned to the minute) matching the cron expression. None if none matches in ~1 year
    or the expression is invalid. Minute-by-minute search (bounded) — inexpensive for occasional use."""
    fields = _cron_fields(expr)
    if fields is None:
        return None
    (mins, _, _), (hours, _, _), (doms, dom_r, _), (months, _, _), (dows, dow_r, _) = fields
    # Start at the next full minute after `after`.
    t = (int(after) // 60 + 1) * 60
    cap = t + 366 * 86400
    while t <= cap:
        lt = time.localtime(t)
        # cron: if dom AND dow are restricted, match if EITHER matches (standard semantics).
        dow0 = lt.tm_wday  # Monday=0..Sunday=6
        cron_dow = (dow0 + 1) % 7  # cron: Sunday=0..Saturday=6
        dom_ok = lt.tm_mday in doms
        dow_ok = cron_dow in dows
        day_ok = (dom_ok or dow_ok) if (dom_r and dow_r) else (dom_ok and dow_ok)
        if lt.tm_min in mins and lt.tm_hour in hours and lt.tm_mon in months and day_ok:
            return float(t)
        t += 60
    return None


# ── CRUD for scheduled tasks (backed by memory.journal) ───────────────────────────────────────────
def create(prompt: str, schedule: str, name: str = "", repeat: str = "",
           now: float | None = None) -> dict:
    """Schedule a task. Return {'ok':bool,'id':int|None,'schedule':dict|None,'error':str|None,'display':str}."""
    now = time.time() if now is None else now
    # `repeat` inherited from the Hermes brief: if provided, force interval recurrence.
    spec = schedule
    if repeat and not _RE_EVERY.match((schedule or "").strip()):
        spec = f"every {repeat}"
    sch = parse_schedule(spec, now=now)
    if sch is None:
        return {"ok": False, "id": None, "schedule": None,
                "error": f"schedule no reconocido: {schedule!r}", "display": ""}
    title = (name or prompt or "recordatorio").strip()[:120]
    detail = {"kind": _KIND, "schedule": sch, "prompt": (prompt or "").strip(),
              "name": (name or "").strip(), "fire_count": 0}
    jid = _journal.add(title, status="pending", detail=detail)
    return {"ok": True, "id": jid, "schedule": sch, "error": None, "display": sch.get("display", "")}


def _scheduled(entries: list[dict]) -> list[dict]:
    return [e for e in entries if (e.get("detail") or {}).get("kind") == _KIND]


def list_jobs(active_only: bool = True) -> list[dict]:
    """Scheduled tasks in a user-friendly view (for the brain brief / verification)."""
    entries = _journal.list_entries(status="pending" if active_only else None)
    out = []
    for e in _scheduled(entries):
        d = e["detail"]
        sch = d.get("schedule") or {}
        out.append({
            "id": e["id"], "name": d.get("name") or e["title"], "prompt": d.get("prompt") or "",
            "schedule": sch.get("display") or "", "type": sch.get("type"),
            "next_run": sch.get("next_run"), "status": e["status"], "fire_count": d.get("fire_count", 0),
        })
    return out


def for_brain() -> str:
    """Startup brief for the brain: active scheduled tasks (or empty if none). Same role as Hermes's cron brief
    had in the kickoff — with nothing to show, it adds no noise to the prompt."""
    jobs = list_jobs(active_only=True)
    if not jobs:
        return ""
    lines = ["[SCHEDULED TASKS — your own reminders/proactive jobs; mention only if relevant]"]
    for j in jobs[:12]:
        when = j.get("schedule") or "?"
        what = (j.get("name") or j.get("prompt") or "recordatorio").strip()
        lines.append(f"  · {what} — {when}")
    return "\n".join(lines)


def due(now: float | None = None) -> list[dict]:
    """OVERDUE scheduled tasks (pending, next_run <= now). Return the journal entries (with detail)."""
    now = time.time() if now is None else now
    out = []
    for e in _scheduled(_journal.list_entries(status="pending")):
        nr = (e["detail"].get("schedule") or {}).get("next_run")
        if isinstance(nr, (int, float)) and nr <= now:
            out.append(e)
    return out


def mark_fired(entry: dict, now: float | None = None) -> dict | None:
    """Mark a task as triggered. One-time → status='done'. Recurring → recalculate next_run (remains pending).
    Return the new schedule (or None if it closed)."""
    now = time.time() if now is None else now
    d = dict(entry["detail"])
    sch = d.get("schedule") or {}
    d["fire_count"] = int(d.get("fire_count", 0)) + 1
    d["last_fired"] = int(now)
    nxt = _advance(sch, now)
    if nxt is None:
        d["schedule"] = sch
        _journal.update(entry["id"], status="done", detail=d)
        return None
    d["schedule"] = nxt
    _journal.update(entry["id"], status="pending", detail=d)
    return nxt


def cancel(ref: str) -> bool:
    """Cancel a task by name (or numeric id). Return True if any task was canceled."""
    ref = (ref or "").strip()
    if not ref:
        return False
    hit = False
    for e in _scheduled(_journal.list_entries(status="pending")):
        d = e["detail"]
        if str(e["id"]) == ref or (d.get("name") or "").strip().lower() == ref.lower() \
                or (e.get("title") or "").strip().lower() == ref.lower():
            _journal.update(e["id"], status="done", detail=d)
            hit = True
    return hit
