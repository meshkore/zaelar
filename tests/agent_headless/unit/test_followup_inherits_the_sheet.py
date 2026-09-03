"""A FOLLOW-UP of a just-ended errand inherits its sheet instead of opening a second box (V2-566).

Measured 2026-09-03, Soria reservation session (events table): task 1 delivered its report at 14:49:13 and
died; the operator answered «coge otro. no pares hasta que tengas una reserva» at 14:52:47; the relaunch
minted a fresh task and a fresh `results--bedf62-2` sheet, leaving `results--bedf62-1` orphaned on screen —
two boxes for one reservation. The live dedup was right to miss (nothing was live); what was missing is the
notch the relay already has in `sheets.py`: «a relay is not a new errand» — and neither is a follow-up.

`dedup.continues_ended` is PURE over the ended snapshots it is handed, and uses the SAME matcher as the live
scan — `test_one_yardstick_of_similarity` is the reason there is no second bar to tune here.
"""
from nucleo import dedup

# The REAL goals from the incident (memory/_data/zaelar.db): task 1's goal and the brain's re-escalation.
ENDED_GOAL = ("Reservar una mesa para comer mañana (viernes 4 de septiembre de 2026, hora de comer) en Soria, "
              "en un restaurante con valoración de más de 4 estrellas en Google")
FOLLOWUP = ("Reservar una mesa para comer el viernes 4 de septiembre de 2026 (mañana), hora de comida (sobre "
            "las 14:00), en un restaurante de Soria con más de 4 estrellas en Google")
UNRELATED = "búscame un fontanero que pueda venir hoy a casa a mirar una fuga"


def test_the_followup_inherits_the_ended_errands_sheet():
    ended = [{"id": "1", "goal": ENDED_GOAL, "sheet": "bedf62-1"}]
    sheet, ev = dedup.continues_ended(FOLLOWUP, "web", ended)
    assert sheet == "bedf62-1", f"the follow-up did not inherit the box: {ev}"
    assert ev.get("from") == "1"


def test_an_unrelated_errand_keeps_its_own_sheet():
    ended = [{"id": "1", "goal": ENDED_GOAL, "sheet": "bedf62-1"}]
    sheet, ev = dedup.continues_ended(UNRELATED, "web", ended)
    assert sheet == "", f"an unrelated errand inherited a box it does not continue: {ev}"


def test_an_ended_errand_without_a_sheet_offers_nothing():
    # An errand that never wrote to a box has no box to inherit — even for a perfect goal match.
    ended = [{"id": "1", "goal": ENDED_GOAL, "sheet": ""}]
    sheet, _ = dedup.continues_ended(FOLLOWUP, "web", ended)
    assert sheet == ""


def test_empty_snapshots_are_a_quiet_no():
    assert dedup.continues_ended(FOLLOWUP, "web", []) == ("", {})
    assert dedup.continues_ended("", "web", [{"id": "1", "goal": ENDED_GOAL, "sheet": "s"}])[0] == ""


def test_the_ended_snapshot_actually_carries_the_sheet(monkeypatch):
    # The V2-199 lesson, in this very function: a wiring test that places snapshots by hand proves nothing
    # about what production stores. `_remember_ended` is the ONLY writer of `_ENDED_SESSIONS`, so if it does
    # not record the sheet, `continues_ended` scans snapshots that can never match — quietly.
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord

    monkeypatch.setattr(dispatch, "_ENDED_SESSIONS", {})
    rec = SessionRecord(task_id="9", goal=ENDED_GOAL, kind="web", sheet="bedf62-9", surface="lista")
    dispatch._remember_ended(rec)
    snap = dispatch._ENDED_SESSIONS.get("9") or {}
    assert snap.get("sheet") == "bedf62-9", f"the snapshot lost the box: {snap}"
    # …and an errand whose surface never was the sheet offers no box to inherit.
    rec2 = SessionRecord(task_id="10", goal=ENDED_GOAL, kind="web", sheet="bedf62-10", surface="voz")
    dispatch._remember_ended(rec2)
    assert (dispatch._ENDED_SESSIONS.get("10") or {}).get("sheet") == ""
