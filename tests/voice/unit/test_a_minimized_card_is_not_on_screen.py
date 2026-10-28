"""A minimized card is open on the canvas and NOT in front of him (demo pass 2026-09-28, full27 S1: «so how did the
monitors go, show me» was suppressed as «already open» over the minimized sheet, and «here they are» spoke over
nothing visible). The canvas report carries which cards are minimized; the one door lets a show through for them."""

import pytest

from nucleo.flash import canvas_visibility as cv


@pytest.fixture
def state(monkeypatch):
    from memory import api
    st = {"open_widgets": ["results"], "minimized_widgets": ["results"]}
    monkeypatch.setattr(api, "state", lambda: st)
    return st


def test_a_show_goes_through_for_a_minimized_card(state, monkeypatch):
    from nucleo.acts import canvas_turn as canvas_arbiter          # the turn asked to see it: the licence the armed door reads
    monkeypatch.setattr(canvas_arbiter, "request_for", lambda extra=None: {
        "text": "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("show", 0.9)}})
    ev = []
    assert cv.present("results::abc-ls1", reason="turn-order", emit=lambda k, l, extra=None: ev.append(l)) is True
    assert ev == ["show"]


def test_an_open_visible_card_is_still_not_raised_again(state):
    state["minimized_widgets"] = []
    ev = []
    assert cv.present("results", reason="turn-order", emit=lambda k, l, extra=None: ev.append(l)) is False
