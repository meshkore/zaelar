"""«I've removed it from your agenda» with no call is the cancellation of the appointment in focus (2026-10-10).

Use case `agenda-appointment-lifecycle`, EN: after writing and moving «Car service at the garage», «You know what,
cancel it. I'll call them myself.» was answered «Okay, I've removed it from your agenda.» with NO call; the
appointment and its notice stayed. No card was named (screen verdict `none` 0.56, catalogue `contactos` 0.32), so the
promise repair never ran, and a CLAIM is not a promise to `reply_promise`. Node 2.402; neighbours measured: the same
claim in Spanish, a named appointment, a list row, a notice, something that is not an appointment, a question, a
refusal, a stale bare «Done.», and the cancel taking its notice (V2-473).
"""
from __future__ import annotations

import time

import pytest


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """An ISOLATED agenda store — never the operator's."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def put(db):
        store.save("agenda", {"meetings": [], **db})
    return put


# ── 2.402 · a claimed removal with no call is the cancellation of the appointment in focus ─────────────────────

def _db(focus_age=20.0):
    now = time.time()
    return {"meetings": [{"title": "Car service at the garage", "date": "2026-10-20", "startTime": "17:00"},
                         {"title": "Dentist", "date": "2026-10-22", "startTime": "10:00"}],
            "focus": {"title": "Car service at the garage", "at": now - focus_age}}, now


def test_the_measured_english_claim_cancels_the_appointment_in_focus():
    from nucleo.flash import agenda_claims as ac
    db, now = _db()
    got = ac.cancel_call("You know what, cancel it. I'll call them myself.",
                         "Okay, I've removed it from your agenda.", db, now=now)
    assert got == {"widget_id": "agenda", "action": "cancel_meeting",
                   "payload": {"title": "Car service at the garage", "date": "2026-10-20"}}


def test_the_spanish_claim_too():
    from nucleo.flash import agenda_claims as ac
    db, now = _db()
    got = ac.cancel_call("Pues mira, al final anúlala, ya llamaré yo.", "Vale, la quito del 20 de octubre.", db, now=now)
    assert got and got["payload"]["title"] == "Car service at the garage"


def test_a_named_appointment_wins_over_the_one_in_focus():
    from nucleo.flash import agenda_claims as ac
    db, now = _db()
    got = ac.cancel_call("Cancel the dentist", "Done, I've cancelled the dentist.", db, now=now)
    assert got and got["payload"] == {"title": "Dentist", "date": "2026-10-22"}


@pytest.mark.parametrize("said, reply", [
    ("Remove the milk from the shopping list", "I've removed it from your list."),     # a list row
    ("Quita la tarea dos de la compra", "Vale, la quito."),                             # a list row, ES
    ("Cancel the reminder", "Okay, I've cancelled it."),                                # a notice, not the meeting
    ("Cancel my flight", "Done, I've cancelled it."),                                   # not one of his appointments
    ("Cancel it", "Should I remove it from your agenda?"),                              # asks
    ("Cancel it", "I can't remove it right now."),                                      # refuses
    ("What time is it?", "I've removed it."),                                           # no removal ordered
])
def test_what_is_not_the_appointment_is_never_cancelled(said, reply):
    from nucleo.flash import agenda_claims as ac
    db, now = _db()
    assert ac.cancel_call(said, reply, db, now=now) is None


def test_a_bare_done_long_after_the_appointment_is_not_it():
    from nucleo.flash import agenda_claims as ac
    db, now = _db(focus_age=400)
    assert ac.cancel_call("cancel it", "Done.", db, now=now) is None
    assert ac.cancel_call("cancel it", "I've removed it from your agenda.", db, now=now) is not None


def test_both_channels_back_the_claim_before_the_model_repair():
    from tests.voice_turn_source import getsource
    from nucleo.flash import post_stream_words, probe_mirrors
    for mod in (probe_mirrors, post_stream_words):
        assert "_agc.or_repair(" in getsource(mod)


def test_the_cancellation_takes_its_notice(agenda, monkeypatch):
    """V2-473 — run for real against the isolated agenda: the claimed cancel is executed and its alarm goes with it."""
    from nucleo import scheduler as S
    from nucleo.flash import agenda_claims as ac
    from widgets import store
    from widgets.agenda import data as d
    made, cancelled = [], []
    monkeypatch.setattr(S, "create", lambda prompt, stamp, **k: made.append(stamp) or {"ok": True, "id": "7",
                                                                                       "display": stamp})
    monkeypatch.setattr(S, "cancel", lambda name, *a, **k: cancelled.append(name) or True)
    monkeypatch.setattr(S, "supersede_loose_notices", lambda *a, **k: None)
    agenda({})
    d.apply_action("add_meeting", {"title": "Car service at the garage", "date": "2027-10-20", "startTime": "17:00"})
    call = ac.cancel_call("You know what, cancel it.", "Okay, I've removed it from your agenda.")
    assert call and call["payload"]["title"] == "Car service at the garage"
    d.apply_action(call["action"], call["payload"])
    db = store.load("agenda")
    assert not db["meetings"] and cancelled, (db.get("meetings"), cancelled)


def test_a_claim_costs_no_model_pass_and_anything_else_still_gets_the_repair(agenda):
    import asyncio

    from nucleo.flash import agenda_claims as ac
    db, _now = _db(focus_age=5)
    agenda(db)
    asked = []

    async def _repair():
        asked.append(1)
        return {"widget_id": "x", "action": "y", "payload": {}}
    got = asyncio.run(ac.or_repair("cancel it", "I've removed it from your agenda.", lambda: _repair()))
    assert got["action"] == "cancel_meeting" and not asked
    got = asyncio.run(ac.or_repair("play some jazz", "Putting some jazz on.", lambda: _repair()))
    assert got["widget_id"] == "x" and asked == [1]
    assert asyncio.run(ac.or_repair("play some jazz", "Putting some jazz on.", lambda: None)) is None
