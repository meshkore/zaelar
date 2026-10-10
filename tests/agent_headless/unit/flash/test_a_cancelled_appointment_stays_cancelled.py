"""An appointment he cancelled stays cancelled, and «I've removed it» is backed by the cancellation (2026-10-10).

Use case `agenda-appointment-lifecycle` (add → move to 17:00 → cancel), red in both languages on 2026-10-10:

  ES — t1 the model WROTE the appointment, t2 moved it, t3 cancelled it (to the trash). On t4 («Perfecto, gracias.
       Nos vemos.») the dated-note backstop re-read t1 from the window and wrote it AGAIN — «confirmed», with a live
       notice on the 20th at 09:00, titled «una revision del coche en el taller el 20 de octubre a las diez de la».
       `already_in_agenda` only saw rows still in the agenda on that day; the trash was invisible to it.
  EN — t3 «You know what, cancel it.» → «Okay, I've removed it from your agenda.» with no call; the appointment and
       its notice stayed. No card was named (screen verdict `none` 0.56, catalogue `contactos` 0.32), so the promise
       repair never ran, and a CLAIM is not a promise to `reply_promise`.

Node 2.400 (the backstop); 2.401 (the title) and 2.402 (the claim) live in their own files.
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
