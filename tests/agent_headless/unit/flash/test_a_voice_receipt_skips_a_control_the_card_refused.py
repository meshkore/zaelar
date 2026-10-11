"""The voice receipt names only the controls that HAPPENED (2026-10-11).

`canvas_focus` records `data:<act>` when the order is emitted — before the detached dispatch — so a `next` the card
refused («No hay más vídeos en la lista», `action_failed`) still counted as done and the transport receipt could name
what was «playing now» over it. A refused control is dropped from `this_turn_acts`.

Disarm: with the `(base, action) in failed` skip removed from `this_turn_acts` the first test goes red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import canvas_focus as CF
from nucleo.flash import transport_receipt as TR


@pytest.fixture(autouse=True)
def fresh():
    CF._reset()
    yield
    CF._reset()


def _turn(*events):
    CF.note("transcript", "", role="user")
    for label, extra in events:
        CF.note("widget", label, extra=extra)


def test_a_control_the_card_refused_is_not_a_control_this_turn_ran():
    _turn(("data:next", {"id": "youtube", "src": "probe", "action": "next"}),
          ("action_failed", {"id": "youtube", "action": "next", "error": "end_of_list"}))
    assert CF.this_turn_acts() == []


def test_a_control_that_ran_is_kept_and_a_new_turn_forgets_the_refusal():
    _turn(("data:next", {"id": "youtube", "src": "probe"}),
          ("action_failed", {"id": "youtube", "action": "next"}))
    _turn(("data:pause", {"id": "youtube", "src": "probe"}), ("data:next", {"id": "musica", "src": "probe"}))
    assert sorted(CF.this_turn_acts()) == [("musica", "control", "next"), ("youtube", "control", "pause")]


def test_the_voice_receipt_owes_nothing_for_a_refused_move(monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "load", lambda wid, *a, **k: {"list": [{"title": "X"}], "pos": 0, "title": "X"})
    _turn(("data:next", {"id": "youtube", "src": "probe"}),
          ("action_failed", {"id": "youtube", "action": "next"}))
    assert asyncio.run(TR.voice_owed_settled("Vale.")) == ""
