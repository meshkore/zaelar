"""nucleo/pulse/scheduler.py — the brain v2's OWN cron (V2-005 · T71).

Scheduled tasks are persisted in `memory.journal` and fired by the orchestrator loop (`nucleo/pulse/loop.py`,
~1 Hz), in our own process. `schedule` formats (language-agnostic parser):
  - **one-time, relative**: `"30m"`, `"2h"`, `"1d"`, `"45s"` (also `"en 30m"`, `"in 2h"`, `"+1h"`).
  - **one-time, ABSOLUTE DATE** (V2-121): `"2026-08-19 09:00"` / `"2026-08-19T09:00"` / `"2026-08-19"` (→ 09:00).
    Without it «recuérdamelo el miércoles» could only be a recurring cron or a fragile `2d`.
  - **recurring by interval**: `"every 30m"`, `"cada 2h"`.
  - **cron 5-campos**: `"0 9 * * *"` (min hora dom mes dow; soporta `* , - /`).

A fired task delivers its `prompt` through the proactive rails (voice + UI); no agent runs per task.
This module is the public face and owns the state; parsing, spoken dates and loose-notice dedupe live in
`scheduler_cron`, `scheduler_when` and `scheduler_notices`, re-exported at the bottom.
"""
from __future__ import annotations

import re
import time

from memory import journal as _journal
from nucleo import consequence as _consequence

_KIND = "scheduled"

# Time units → seconds (language-agnostic parser).
_UNIT_S = {"s": 1, "sec": 1, "m": 60, "min": 60, "h": 3600, "hr": 3600, "d": 86400, "day": 86400}

_RE_EVERY = re.compile(r"^(?:every|cada)\s+(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", re.I)
_RE_ONCE = re.compile(r"^(?:in\s+|en\s+|\+)?(\d+)\s*(s|sec|m|min|h|hr|d|day)s?$", re.I)
# ABSOLUTE date (V2-121): ISO ONLY — the prompt already lists today's/tomorrow's dates in ISO, and an ambiguous
# local format (19/08 vs 08/19) is rejected on purpose.
_RE_ABS = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{1,2}):(\d{2}))?$")
_DEFAULT_HOUR = 9          # a day without a time rings in the morning

# Spoken-date tables for `scheduler_when.parse_when` (the backstop's resolver, V2-146).
_WEEKDAYS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6,
             "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
# «mañana» as the NOUN *morning* — see `parse_when`. Always determined; the adverb *tomorrow* never is.
_RE_MORNING_NOUN = re.compile(r"\b(?:por\s+la|de\s+la|a\s+la|en\s+la|la|una|media|esta|toda\s+la)\s+manana\b", re.I)
_RE_AT_HOUR = re.compile(r"\ba\s+las?\s+(\d{1,2})(?::(\d{2}))?\b|\bat\s+(\d{1,2})(?::(\d{2}))?\b", re.I)
_RE_DAY_OF_MONTH = re.compile(r"\bel\s+d[ií]a\s+(\d{1,2})\b|\bon\s+the\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.I)
_MONTHS = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
           "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
           "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7, "august": 8,
           "september": 9, "october": 10, "november": 11, "december": 12,
           "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
           "nov": 11, "dec": 12}
_M = "|".join(sorted(_MONTHS, key=len, reverse=True))
_RE_DAY_MONTH = re.compile(rf"\b(\d{{1,2}})\s+(?:de\s+)?({_M})\b\.?(?:,?\s+(?:de\s+|del\s+)?(\d{{4}}))?")
_RE_MONTH_DAY = re.compile(rf"\b({_M})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?")

_FIELD_BOUNDS = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]  # 5-field cron; dow: 0=Sunday


# ── CRUD for scheduled tasks (backed by memory.journal) ───────────────────────────────────────────
@_consequence.door("cron.create", neutral=lambda prompt="", schedule="", *_a, **_k: {
    "ok": True, "id": None, "schedule": None, "error": None, "display": schedule, "dry": True})
def create(prompt: str, schedule: str, name: str = "", repeat: str = "",
           now: float | None = None, origin: str = "cron") -> dict:
    """Schedule a task. Return {'ok':bool,'id':int|None,'schedule':dict|None,'error':str|None,'display':str}.

    `origin` says WHO asked for the clock (V2-728): an appointment's own notice (`origin="agenda"`) is not
    painted back as a system task; everything else is `cron` («avísame cada lunes»).
    """
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
              "name": (name or "").strip(), "fire_count": 0,
              "origin": (origin or "cron").strip().lower() or "cron"}
    jid = _journal.add(title, status="pending", detail=detail)
    _board(jid)
    return {"ok": True, "id": jid, "schedule": sch, "error": None, "display": sch.get("display", "")}


def _scheduled(entries: list[dict]) -> list[dict]:
    return [e for e in entries if (e.get("detail") or {}).get("kind") == _KIND]


def pending_carrying(key: str) -> list[dict]:
    """Pending scheduled jobs whose detail carries `key`, raw — for the module that put it there (quota_wait's
    `resume_errand`), so the journal stays behind this file instead of being read from a third place."""
    return [e for e in _scheduled(_journal.list_entries(status="pending")) if (e.get("detail") or {}).get(key)]


def annotate(jid, **fields) -> None:
    """Merge `fields` into a scheduled job's detail (what a caller needs back when it fires)."""
    entry = _journal.get(int(jid)) or {}
    _journal.update(int(jid), detail={**(entry.get("detail") or {}), **fields})


# ── the operator's BOARD (V2-728) ─────────────────────────────────────────────────────────────────────────
# A scheduled job is a commission with a clock on it: `nucleo/circuit/ledger.py` owns the translation, this
# file owns WHEN. One function for every mutation point, so no writer can forget it.
def _board(jid) -> None:
    try:
        from nucleo.circuit import ledger as _tasks
        entry = _journal.get(int(jid))
        if entry:
            _tasks.scheduled_mirrored(entry)
    except Exception:  # noqa: BLE001 — a board that failed to update must never lose the reminder
        pass
    try:
        from nucleo.pulse import wake        # V2-796 — the next due instant may have moved: report it (debounced)
        wake.note_changed()
    except Exception as e:  # noqa: BLE001 — the reminder is stored; only the wake report may lag a pulse
        __import__("logging").getLogger("zaelar.scheduler").debug(f"scheduler: wake note failed: {e!r}")


def next_due() -> float | None:
    """The earliest `next_run` among pending jobs, or None (V2-796: what a stopped machine must wake up for)."""
    best = None
    for e in _scheduled(_journal.list_entries(status="pending")):
        nr = (e["detail"].get("schedule") or {}).get("next_run")
        if isinstance(nr, (int, float)) and (best is None or nr < best):
            best = float(nr)
    return best


def reconcile_board() -> int:
    """Put every PENDING job on the board. Returns how many, so it can be counted rather than assumed.

    Called once at startup: jobs older than the board, and the self-heal for any write whose mirror failed
    (which is why the mirror may fail soft).
    """
    n = 0
    try:
        for e in _scheduled(_journal.list_entries(status="pending")):
            _board(e["id"])
            n += 1
    except Exception:  # noqa: BLE001
        return n
    return n


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
    """Startup brief for the brain: active scheduled tasks, or "" so an empty list adds no prompt noise."""
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
        _board(entry["id"])
        return None
    d["schedule"] = nxt
    _journal.update(entry["id"], status="pending", detail=d)
    _board(entry["id"])
    return nxt


@_consequence.door("cron.cancel", neutral=True)
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
            _board(e["id"])
            hit = True
    return hit


from nucleo.pulse.scheduler_cron import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _advance, _cron_fields, _parse_field, next_cron, parse_schedule)
from nucleo.pulse.scheduler_notices import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _refresh_loose_notice, create_unless_ringing, supersede_loose_notices)
from nucleo.pulse.scheduler_when import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _day_and_month, _strip_accents_sched, dated_mentions, parse_when)
