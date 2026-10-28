"""nucleo/pulse/scheduler_notices.py — one ask, one alarm: the prose backstop's loose «aviso» vs a live job.

The journal, `_board` and `_KIND` live in `scheduler` (`_m`).
"""
from __future__ import annotations



def create_unless_ringing(prompt: str, schedule: str, name: str = "") -> dict:
    """`create`, unless a live job already rings at that instant — then that job answers (V2-781 pair 3: the
    worker re-scheduled the premiere the turn had already set, two alarms for one ask)."""
    disp = (_m.parse_schedule(schedule) or {}).get("display") or ""
    live = next((j for j in _m.list_jobs(active_only=True) if disp and str(j.get("schedule") or "") == disp), None)
    if live:
        _m._refresh_loose_notice(live, prompt)
        return {"ok": True, "id": live.get("id"), "display": disp, "existed": True, "error": None}
    return _m.create(prompt, schedule, name)


def _refresh_loose_notice(live: dict, prompt: str) -> None:
    """The live job keeps its instant, but a prose backstop's loose «aviso» takes the newer, informed text.

    V2-781 pair 3 (`find-a-future-release-and-remind-me`): the worker verified the date and asked for the same
    instant with the confirmed fact; the old job answered, so the fact was dropped and the question rang."""
    prompt = (prompt or "").strip()
    if str(live.get("name") or "").strip() != "aviso" or not prompt or prompt == live.get("prompt"):
        return
    try:
        entry = _m._journal.get(int(live["id"]))
        d = dict((entry or {}).get("detail") or {})
        if d.get("kind") != _m._KIND or (d.get("origin") or "cron") != "cron":
            return
        d["prompt"] = prompt
        _m._journal.update(entry["id"], status="pending", detail=d)
        _m._board(entry["id"])
    except Exception:  # noqa: BLE001 — the notice still rings with its old text
        return


def supersede_loose_notices(display: str, *, within_s: float = 180.0, now: float | None = None) -> list:
    """Retire the prose backstop's loose «aviso» at the SAME instant an appointment's notice was just scheduled.

    V2-781 T519 (`dentist-appointment-into-agenda`, ES): the agenda moved the notice to 12:00 and, 8 ms earlier,
    the backstop had set its own «aviso» at 12:00 — two alerts. The backstop already skips a moment a live job
    covers; this is the other order. Bounded: only `aviso` (origin cron), that exact instant, created in the last
    `within_s` seconds. Returns the ids."""
    import time as _t
    now = _t.time() if now is None else now
    gone = []
    try:
        for e in _m._scheduled(_m._journal.list_entries(status="pending")):
            d = e["detail"]
            if ((d.get("name") or "").strip() == "aviso" and (d.get("origin") or "cron") == "cron"
                    and (d.get("schedule") or {}).get("display") == display
                    and now - float(e.get("created") or 0) <= within_s):
                _m._journal.update(e["id"], status="done", detail=d)
                _m._board(e["id"])
                gone.append(e["id"])
    except Exception:  # noqa: BLE001 — a notice too many is better than a lost one
        return gone
    return gone


# Last, so either import order works: `_m` is only read at call time.
from nucleo.pulse import scheduler as _m  # noqa: E402
