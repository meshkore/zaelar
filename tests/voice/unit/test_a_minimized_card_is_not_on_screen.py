from tests import voice_turn_source as _vts
"""A minimized card is open on the canvas and NOT in front of him (demo pass 2026-09-28, full27 S1: «so how did the
monitors go, show me» was suppressed as «already open» over the minimized sheet, and «here they are» spoke over
nothing visible). The canvas report carries which cards are minimized; the one door lets a show through for them."""
import pathlib

import pytest

from nucleo.flash import canvas_visibility as cv


@pytest.fixture
def state(monkeypatch):
    from memory import api
    st = {"open_widgets": ["results"], "minimized_widgets": ["results"]}
    monkeypatch.setattr(api, "state", lambda: st)
    return st


def test_a_show_goes_through_for_a_minimized_card(state):
    ev = []
    assert cv.present("results::abc-ls1", reason="turn-order", emit=lambda k, l, extra=None: ev.append(l)) is True
    assert ev == ["show"]


def test_an_open_visible_card_is_still_not_raised_again(state):
    state["minimized_widgets"] = []
    ev = []
    assert cv.present("results", reason="turn-order", emit=lambda k, l, extra=None: ev.append(l)) is False


def test_the_canvas_report_records_the_minimized_cards():
    src = _vts.read(pathlib.Path(__file__).resolve().parents[3] / "server/voice_api.py")
    assert '"minimized_widgets": _minw' in src and 'it.get("min")' in src
