"""«Show me the chart» opens it, and the answer does not say it cannot show it (demo pass 2026-09-28, full17 M1).

The answer composed from the card's data was told whether the card is on screen by the canvas report — which
comes from the browser and lags the very turn that presents the card. So it said «I can't pull up the chart
itself here» over the chart. A card THIS turn brought counts as on screen."""
from tests import voice_turn_source as _vts
import pytest

from nucleo import canvas_focus as cf
from nucleo.flash import canvas_visibility as cvis
from nucleo.flash import direct_action as da


@pytest.fixture
def closed_report(monkeypatch):
    monkeypatch.setattr(cvis, "is_open", lambda wid, known=None: False)
    cf.note("transcript", "", role="user")          # a new turn starts


def test_the_card_this_turn_presented_is_on_screen(closed_report):
    cf.note("widget", "show", extra={"id": "markets", "src": "flash"})
    assert da.on_screen_now("markets") is True


def test_a_card_nobody_brought_is_not(closed_report):
    assert da.on_screen_now("markets") is False


def test_the_voice_answer_reads_it():
    import pathlib
    src = _vts.read(pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py")
    assert "answered=True, on_screen=_direct_action.on_screen_now(_op_answer[0])" in src
