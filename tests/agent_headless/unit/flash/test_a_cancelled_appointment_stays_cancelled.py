"""An appointment he cancelled stays cancelled, and «I've removed it» is backed by the cancellation (2026-10-10).

Use case `agenda-appointment-lifecycle` (add → move to 17:00 → cancel), red in both languages on 2026-10-10:

  ES — t1 the model WROTE the appointment, t2 moved it, t3 cancelled it (to the trash). On t4 («Perfecto, gracias.
       Nos vemos.») the dated-note backstop re-read t1 from the window and wrote it AGAIN — «confirmed», with a live
       notice on the 20th at 09:00, titled «una revision del coche en el taller el 20 de octubre a las diez de la».
       `already_in_agenda` only saw rows still in the agenda on that day; the trash was invisible to it.
  EN — t3 «You know what, cancel it.» → «Okay, I've removed it from your agenda.» with no call; the appointment and
       its notice stayed. No card was named (screen verdict `none` 0.56, catalogue `contactos` 0.32), so the promise
       repair never ran, and a CLAIM is not a promise to `reply_promise`.

Nodes 2.400 (the backstop) and 2.402 (the claim); 2.401 (the title) lives in tests/browser/unit/agenda.
"""
from __future__ import annotations

import time

import pytest

T1_ES = "Apúntame una revisión del coche en el taller el 20 de octubre a las diez de la mañana."
WINDOW_ES = [
    {"role": "user", "content": T1_ES}, {"role": "assistant", "content": "Hecho."},
    {"role": "user", "content": "Ah, mejor ponla a las cinco de la tarde ese mismo día."},
    {"role": "assistant", "content": "Hecho."},
    {"role": "user", "content": "Pues mira, al final anúlala, ya llamaré yo."},
    {"role": "assistant", "content": "Vale, la quito del 20 de octubre."},
    {"role": "user", "content": "Perfecto, gracias. Nos vemos."},
]
FAREWELL = ("¡Hasta luego! Aquí estaré cuando me necesites.", "Perfecto, gracias. Nos vemos.")


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    """An ISOLATED agenda store — never the operator's."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def put(db):
        store.save("agenda", {"meetings": [], **db})
    return put


def _trash(title, date, start="17:00", age=20.0):
    return {"at": time.time() - age, "kind": "delete", "label": title,
            "rows": [{"title": title, "date": date, "startTime": start, "status": "confirmed"}]}


# ── 2.400 · the backstop never writes back what he cancelled or moved ──────────────────────────────────────────

def test_the_measured_transcript_writes_nothing_after_the_cancellation(agenda):
    from nucleo.flash import note_backstop as nb
    agenda({"meetingTrash": [_trash("Revisión del coche en el taller", "2026-10-20")]})
    assert nb.note_to_file(*FAREWELL, window=WINDOW_ES) is None


def test_without_the_cancellation_the_backstop_still_backs_the_promise(agenda):
    """The neighbour that must keep working: nothing written, nothing cancelled → the entry is written, with a
    title that says what and the hour it said."""
    from nucleo.flash import note_backstop as nb
    agenda({})
    note = nb.note_to_file(*FAREWELL, window=WINDOW_ES)
    assert note and note["date"] == "2026-10-20"
    assert note["title"].lower() == "revision del coche en el taller" and note["startTime"] == "10:00"


def test_a_moved_appointment_is_not_written_back_on_its_old_day(agenda):
    from nucleo.flash import note_backstop as nb
    agenda({"meetings": [{"title": "Revisión del coche en el taller", "date": "2026-10-21", "startTime": "17:00"}],
            "focus": {"title": "Revisión del coche en el taller", "at": time.time() - 30}})
    assert nb.note_to_file(*FAREWELL, window=WINDOW_ES) is None


def test_an_old_cancellation_of_another_day_does_not_block_a_new_entry(agenda):
    """The trash is one conversation's memory on other days: last month's cancelled car service on the 3rd does not
    stop him writing one on the 20th."""
    from nucleo.flash import note_backstop as nb
    agenda({"meetingTrash": [_trash("Revisión del coche en el taller", "2026-09-03", age=40 * 86400)]})
    assert nb.note_to_file(*FAREWELL, window=WINDOW_ES) is not None


def test_both_channels_ask_the_one_decision():
    from tests.voice_turn_source import getsource
    from nucleo.flash import post_stream_words, probe_scheduling
    for mod in (probe_scheduling, post_stream_words):
        assert "note_backstop" in getsource(mod) and "note_to_file(" in getsource(mod)


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
        assert "agenda_claims" in getsource(mod) and "cancel_call(" in getsource(mod)


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
