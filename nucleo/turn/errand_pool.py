"""The errands a sentence can name besides the live and parked ones: the one STARTING and the ones just FINISHED.

three-tasks-at-once (2026-10-11 11:34, sandboxes 113340-en / 113401-es). `named_errand.known()` read the dispatcher's
live sessions and the confirmation gate's parked asks — and two errands he talks about were in neither:

  · STARTING. «yeah go ahead, and for the game make the jump feel higher» resolved the parked game (the gate popped
    it) and re-escalated it; the session registered ~1 s later. In between the game was nowhere, so his sentence
    named no errand, and the delivery backstop glued the MONITOR's rows to the reply. `escalate._tasks` holds every
    escalation from the moment it is asked until its session finishes — the gap is exactly that registry.
  · FINISHED. With the report, the monitor and the game all done, «me sacas un LG de 24… ¿Y el Fujitsu P27? Y al
    juego… monedas? Y del informe…» named nothing either; the list lane took the sentence for a NEW list and he got
    «Entendido, me pides varias cosas» twice, his ≥27" complaint never answered. `ended` keeps the just-ended ones.

Same entry shape as `named_errand.known()`; `starting` / `ended` say which kind it is, for callers that care.
"""
from __future__ import annotations

from loguru import logger

#: How long an asked escalation counts as «starting» without a session of its own. A real one registers within
#: seconds; past this it is either running (a session) or was folded into another errand by the dedup.
STARTING_S = 90


def _entry(eid: str, request: str, **extra) -> dict:
    return {"id": str(eid), "label": "", "title": str(extra.pop("title", "") or ""), "request": request.strip(),
            "phase": "", "note": "", "waiting_on": "", "parked": False, "sheet": str(extra.pop("sheet", "") or ""),
            "surface": "", **extra}


def _already(request: str, existing: list[dict]) -> bool:
    from nucleo.turn.errands_of_a_turn import same_errand
    return any(same_errand(request, str(e.get("request") or "")) for e in existing)


def starting(existing: list[dict]) -> list[dict]:
    """Escalations asked in the last `STARTING_S` seconds that no live or parked errand is yet. Never raises."""
    out: list[dict] = []
    try:
        from nucleo.flash import escalate as _esc
        for t in _esc.pending():
            req = str(t.get("request") or "")
            if req and int(t.get("secs") or 0) <= STARTING_S and not _already(req, existing + out):
                out.append(_entry(f"esc:{t.get('id')}", req, starting=True))
    except Exception as e:  # noqa: BLE001 — a reader never breaks a turn
        logger.debug(f"errand_pool: escalations unreadable — {type(e).__name__}: {e}")
    return out


def finished(existing: list[dict]) -> list[dict]:
    """Errands that ENDED recently (the ended-sessions window) and are not live again. Never raises."""
    out: list[dict] = []
    try:
        from nucleo.workers import ended as _ended
        for e in _ended.recently_ended_sessions(limit=6):
            req = str(e.get("goal") or "")
            if req and not _already(req, existing + out):
                out.append(_entry(e.get("id") or "", req, title=e.get("title"), sheet=e.get("sheet"), ended=True))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"errand_pool: ended errands unreadable — {type(e).__name__}: {e}")
    return out
