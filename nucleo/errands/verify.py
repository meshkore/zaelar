"""nucleo/errands/verify.py — has this errand actually been achieved? (V2-683)

The operator's condition: «la tarea no termina hasta que no está correctamente programada esa reunión».
So an errand does not close because a model says so; it closes because the product's own truth says so —
the V2-660 harness's rule, applied to something that lives for hours instead of for one turn.

A CLOSED SET of verifiers, like the harness's: what `done_when` can ask for is what is implemented here,
and anything else answers None. **None means «cannot be read», and an errand with an unreadable condition
is NEVER closed by this** — it ends by its deadline instead. A wrong «done» would tell him a meeting
exists when nothing does, which is the exact lie this whole batch is built against.
"""
from __future__ import annotations

import time

from loguru import logger


def _agenda_rows() -> list[dict] | None:
    try:
        from widgets.agenda import data as agenda
        v = agenda.view_data() or {}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errands.verify: la agenda no se pudo leer ({e!r})")
        return None
    rows = v.get("meetings")
    return list(rows) if isinstance(rows, list) else None


def _within(day: str, start_ts: float, end_ts: float) -> bool:
    lo = time.strftime("%Y-%m-%d", time.localtime(start_ts))
    hi = time.strftime("%Y-%m-%d", time.localtime(end_ts))
    return bool(day) and lo <= day <= hi


def meeting_exists(errand: dict, now: float | None = None) -> bool | None:
    """True when the operator's agenda holds a meeting inside this errand's window that is NOT one it
    already had before the errand started.

    The «not already there» half is what makes it a verification rather than a coincidence: an errand about
    seeing Iván this afternoon must not be closed by the dentist appointment he had booked last week."""
    now = time.time() if now is None else now
    rows = _agenda_rows()
    if rows is None:
        return None                      # unreadable → the harness's rule: stay silent, never guess
    born = float(errand.get("created_at") or 0)
    deadline = float(errand.get("deadline") or now)
    for m in rows:
        if not _within(str(m.get("date") or ""), born, deadline):
            continue
        # A row the errand itself could have produced: created after it opened. The agenda stores a creation
        # date at day granularity, so this is deliberately generous — the cost of missing one is that the
        # errand closes by deadline instead, which is the safe direction.
        created = str(m.get("created") or "")
        if created and created < time.strftime("%Y-%m-%d", time.localtime(born)):
            continue
        if str(m.get("status") or "confirmed") == "cancelled":
            continue
        return True
    return False


#: What a `done_when` may ask for. A spec naming anything else is not executed — «the condition cannot be
#: read» — so a typo in a playbook can never turn into an errand that closes itself for the wrong reason.
_VERIFIERS = {
    ("agenda", "meeting"): meeting_exists,
}


def check(errand: dict, now: float | None = None) -> bool | None:
    """Run this errand's `done_when`. True = achieved · False = not yet · None = cannot be read."""
    spec = errand.get("done_when") or {}
    if not isinstance(spec, dict) or not spec:
        return None
    fn = _VERIFIERS.get((str(spec.get("widget") or ""), str(spec.get("has") or "")))
    if fn is None:
        return None
    try:
        return fn(errand, now)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errands.verify: {spec} falló ({e!r})")
        return None


def sweep_met(now: float | None = None) -> list[dict]:
    """Close every open errand whose objective has actually been achieved. Returns what it closed, so the
    caller can tell him once — «ya está» said by the machine that checked, not by the model that hoped."""
    from . import close, live
    out = []
    for row in live(now):
        if check(row, now) is True:
            closed = close(row["id"], "closed", "la gestión está hecha y verificada")
            if closed:
                out.append(closed)
    return out
