"""The background-task block says whether the errand's sheet is on screen NOW (demo pass 30, S1, 2026-09-28).

«so how did the monitors go, show me» — the monitor sheet had been closed two blocks earlier, the canvas
reported nothing open, and the reply was «The shortlist is on your screen», with nothing opened. The block
carried «YA ENTREGADO (de su hoja)» next to «negar una entrega que el operador tiene delante…», and left WHERE
the sheet was to be assumed. It now states it from the canvas's raw instances; unknown says nothing.
"""
import pytest

from nucleo import dispatch
from nucleo.flash import canvas_visibility as CV
from nucleo.flash import task_block as TB

_SHEET = "results::c29838-ls1"


@pytest.fixture
def _one_task(monkeypatch):
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [
        {"id": "7", "request": "find three 27 inch 4k monitors", "phase": "verifying", "secs": 500,
         "sheet": _SHEET}])
    monkeypatch.setattr(TB, "rows_of_sheet", lambda sheet, n: ["KTC H27P6 — $260.09"])


def _block(monkeypatch, open_now):
    monkeypatch.setattr("server.voice_api.open_instances", lambda: list(open_now))
    return " ".join(TB.pending_task_lines())


def test_a_closed_sheet_is_said_to_be_closed(monkeypatch, _one_task):
    text = _block(monkeypatch, ["results::c29838-9"])       # ANOTHER results card is open, not this one
    assert "NO está en pantalla" in text, text


def test_an_open_sheet_is_said_to_be_open(monkeypatch, _one_task):
    assert "ESTÁ abierta" in _block(monkeypatch, [_SHEET, "agenda"])


def test_an_unknown_canvas_asserts_nothing(monkeypatch, _one_task):
    text = _block(monkeypatch, [])
    assert "NO está en pantalla" not in text and "ESTÁ abierta" not in text


def test_the_instance_is_compared_not_the_base():
    assert CV.card_is_open(_SHEET, known=["results::other"]) is False
    assert CV.card_is_open(_SHEET, known=[_SHEET]) is True
    assert CV.card_is_open(_SHEET, known=[]) is None
