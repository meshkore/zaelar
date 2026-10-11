"""nucleo/flash/reminder_backing.py — the voice channel's half of «a reminder he was told about EXISTS».

Two steps after the reply is spoken, in this order:

  1. the prose backstop (V2-146): a promise or a claim of a dated reminder with no `cron.create` tag in the
     turn becomes the job — `dated_reminder_backstop` decides, the same function the probe calls;
  2. the claim check (2026-10-10, find-a-future-release-and-remind-me EN): a reply that CLAIMS a reminder is set
     while no active job exists owes a correction, which is returned for the caller to say.

The probe channel runs step 1 in `probe_scheduling.py` (it appends a tag the cron executor runs) and step 2 in
`probe_after.the_words_it_owes` (`claim_correction`), after that executor. Same decisions, one place each.
"""
from __future__ import annotations

import logging

from nucleo import scheduler as _sched

from . import reminder_guards as _rg
from . import reminder_promise as _rp
from . import reminder_year as _ry

logger = logging.getLogger(__name__)


def claim_correction(spoken: str, operator_text: str = "", window=None) -> str:
    """The correction a reply owes about a reminder — both channels call this. A promise or claim for a day already
    gone by says so (2026-10-11); a claim with no job behind it says it is not set."""
    if _rp.find(spoken):
        when = _rg.resolved_reminder_moment(spoken, operator_text, window)
        if when and (line := _ry.passed_line(when, spoken, operator_text, window)):
            return line
    return _rp.unbacked_claim_line(spoken)


def back_and_check(spoken: str, operator_text: str, *, window, emit, backstop: bool = True) -> str:
    """Schedule the promised notice when the turn did not; return the correction an unbacked claim owes, or ""."""
    if backstop:
        try:
            cron = _rg.dated_reminder_backstop(spoken, operator_text, window=window)
            if cron:
                r = _sched.create(cron["prompt"], cron["schedule"], name=cron["name"])
                emit("cron", "⏰ aviso programado por backstop (lo prometió sin emitir la tag)"
                     if r.get("ok") else "⚠️ schedule no reconocido",
                     text=r.get("display") or r.get("error") or "", role="system",
                     extra={"ok": bool(r.get("ok")), "op": "cron.create", "backstop": True})
        except Exception as e:  # noqa: BLE001
            logger.warning("reminder backstop failed: %s", e)
    fix = claim_correction(spoken, operator_text, window)
    if fix:
        emit("cron", "⚠️ claimed a reminder that is not scheduled", text=spoken[:160], role="system",
             extra={"op": "claim_check", "ok": False})
    return fix
