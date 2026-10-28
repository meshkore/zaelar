"""While an errand he asked for a NAMED PLACE runs, the introduction does not ask where he lives (node 2.707).

search-restaurant-occasion EN (2026-10-14): «Find me a restaurant for an anniversary in Portland…» was running and
the pack had the reply ask «where are you based these days?» — read beside the errand, his «San Francisco» became
part of it. The location stays on the pack's list and waits for a turn with no such errand.
"""
from __future__ import annotations

import pytest

from nucleo import dispatch
from nucleo.turn.prompt.packs import introduction as I
from nucleo.turn.prompt.packs import place_in_play as P

PORTLAND = {"id": "2", "request": "Find me a restaurant for an anniversary in Portland, quiet, about $60 a person.",
            "phase": "", "waiting_on": ""}


@pytest.fixture
def stranger(monkeypatch):
    monkeypatch.setattr(I, "_known", lambda: {})
    import nucleo.dispatch.confirm as dc
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    return monkeypatch


def test_beside_an_errand_in_portland_the_location_is_not_asked(stranger):
    stranger.setattr(dispatch, "pending_summaries", lambda: [dict(PORTLAND)])
    block = I.block()
    assert "dónde vive" not in block and "su nombre" in block, block


def test_with_no_such_errand_it_still_is(stranger):
    stranger.setattr(dispatch, "pending_summaries", lambda: [])
    assert "dónde vive" in I.block()


@pytest.mark.parametrize("ask,placed", [
    ("Find me a restaurant for an anniversary in Portland", True),
    ("Búscame un piso en alquiler en Valencia", True),
    ("Find me a vintage automatic Seiko for under $450.", False),
    ("Find me an original pressing in good condition", False),
])
def test_a_place_is_read_the_way_a_sentence_marks_one(ask, placed):
    assert P.names_a_place(ask) is placed
