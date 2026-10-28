"""A [[close]] of the agenda over «quita el piano entero» cancels the series — with no verdict to read. Node 2.587.

Measured (agenda-everyday-edits ES, report 20261014-005211, step 14): «Y quita el piano entero, toda la serie» →
«Voy a ello. He cerrado Agenda. Ya no queda nada en pantalla.»: the model emitted [[close]] and called nothing; the
series stayed. The 2026-10-11 fix (2.440–2.444) reads the turn's verdict and backs a «Hecho.» claim; this round the
decision model answered 529 from turn 6 on (every read `off`) and the reply was a promise, so neither held. The
card's own rows decide: a removal that names ONE of its appointments and not the card itself is that appointment's
`cancel_meeting`, on both channels.
"""
from __future__ import annotations

import pathlib

import pytest

from nucleo.flash import agenda_close_is_a_cancel as CC

ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _db():
    series = {"freq": "weekly", "interval": 1, "until": "2027-01-31", "days": [1]}
    return {"meetings": [{"title": "Clase de piano de Abril", "date": "2026-10-20", "startTime": "17:00",
                          "repeat": series},
                         {"title": "Revisión dental con el doctor Ruiz", "date": "2026-10-15", "startTime": "11:30"}]}


def test_the_measured_series_removal_is_its_whole_cancellation():
    got = CC.cancel_instead("Y quita el piano entero, toda la serie", "agenda", _db())
    assert got == {"widget_id": "agenda", "action": "cancel_meeting",
                   "payload": {"title": "Clase de piano de Abril", "whole": True}}


def test_english_and_a_single_appointment():
    db = _db()
    db["meetings"][0]["title"] = "Abril's piano lesson"
    got = CC.cancel_instead("And get rid of the piano completely, the whole series", "agenda", db)
    assert got and got["payload"] == {"title": "Abril's piano lesson", "whole": True}
    got = CC.cancel_instead("quita lo del doctor Ruiz", "agenda", _db())
    assert got and got["payload"] == {"title": "Revisión dental con el doctor Ruiz", "date": "2026-10-15"}


def test_a_series_without_its_scope_keeps_the_question():
    got = CC.cancel_instead("quita el piano", "agenda", _db())
    assert got and got["payload"] == {"title": "Clase de piano de Abril"}


@pytest.mark.parametrize("said,card", [
    ("quita la agenda", "agenda"),                 # names the card: that IS the close
    ("cierra el calendario", "agenda"),
    ("quítalo", "agenda"),                          # names no appointment
    ("quita la canción del piano", "agenda"),       # a song, not an appointment
    ("quita el piano", "musica"),                   # not the agenda
    ("vale, ya la puedes cerrar", "agenda"),        # no removal order
])
def test_the_close_stands(said, card):
    assert CC.cancel_instead(said, card, _db()) is None


def test_took_the_close_runs_the_call(monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: _db() if wid == "agenda" else {})
    ran = []
    assert CC.took_the_close("Y quita el piano entero, toda la serie", {"id": "agenda"}, ran.append) is True
    assert ran and ran[0]["payload"]["whole"] is True
    ran.clear()
    assert CC.took_the_close("quita la agenda", {"id": "agenda"}, ran.append) is False and ran == []


def test_the_voice_turn_asks_the_guard():
    voice = (ENGINE / "nucleo/flash/tool_executor_widget_calls.py").read_text(encoding="utf-8")
    assert "_txw._close_cancel.inside_or_cancelled(_brief, _txw._bnotes.operator_half(text), extra," in voice
