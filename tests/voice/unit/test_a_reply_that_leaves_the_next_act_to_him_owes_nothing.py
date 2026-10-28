"""V2-792 — the promise harness (V2-790) never says «I have not done it» over a reply that is TRUE.

The class, as measured: a search ran and put six numbered videos on screen; the next turn's reply said «they're all
six on screen, numbered — tell me the number and I'll play it». Nothing ran in THAT turn, no second pass had a card,
and the turn end appended «I have not done it: I could not run it from here». Two holes:

  · the reply's verdict read `ask_first` (0.72); below `ASK_FIRST_MIN` it was cached as `act`, and the harness
    asked the phrase tables anyway — «te lo pongo» reads as a promise to them, though the act is HIS next choice;
  · a reply that DESCRIBES the screen an op of this request left there was treated as a claim over nothing.

Since refactor2710-03 the BRIEF decides whether an act was owed (`reply.owes_an_act`), never our words: a turn it does
not read as an order owes nothing, and a claimed state holds when the previous acting turn's own op left its card open
with nothing refused (`canvas_focus.last_turn_held`).
"""
from __future__ import annotations

import pytest

from nucleo import canvas_focus
from nucleo.turn import promise_kept as pk
from nucleo.turn import reply as R

ON_SCREEN = {
    "es": "Ya están los seis en pantalla, numerados; dime el número que quieras y te lo pongo.",
    "en": "All six are on screen, numbered — tell me the number you want and I'll put it on.",
}
CLAIM = {"es": "Ya lo tienes en pantalla, el primero de la lista.", "en": "There it is — it's on your screen."}
PROMISE = {"es": "Te lo pongo ahora mismo.", "en": "I'll put it on right now."}
ORDER = "a brief that reads an order"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    saved = {k: (list(v) if isinstance(v, list) else v) for k, v in canvas_focus._state.items()}
    from nucleo.flash import canvas_visibility
    monkeypatch.setattr(canvas_visibility, "open_ids", lambda: frozenset({"youtube"}))
    monkeypatch.setattr(R, "owes_an_act", lambda brief: "order" if brief == ORDER else "")
    yield
    canvas_focus._state.update(saved)


def _a_search_ran_last_turn(*, refused: bool = False) -> None:
    canvas_focus.note("transcript", "🗣", role="user")
    canvas_focus.note("widget", "data:search", extra={"id": "youtube", "src": "flash"})
    if refused:
        canvas_focus.note("widget", "action_failed", extra={"id": "youtube", "action": "search"})
    canvas_focus.note("transcript", "🗣", role="user")               # his next turn: the reply is about the screen


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_turn_the_brief_does_not_read_as_an_order_owes_nothing_whatever_the_words(lang):
    for reply in (ON_SCREEN[lang], PROMISE[lang], CLAIM[lang]):
        assert pk.close(reply, {}, acted=False, brief=None) == "", "no verdict, nothing invented"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_order_with_nothing_run_is_said_undone(lang):
    canvas_focus._state.update(previous=[], prev_failed=[], current=[])
    assert pk.close(PROMISE[lang], {}, acted=False, brief=ORDER), "an owed act, nothing run: said undone"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_claimed_state_an_op_of_this_request_left_on_screen_holds(lang):
    _a_search_ran_last_turn()
    assert canvas_focus.last_turn_held(["youtube"]) == "youtube"
    assert pk.close(CLAIM[lang], {}, acted=False, brief=ORDER) == ""


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_claim_over_nothing_or_over_a_refused_op_is_still_said_undone(lang):
    canvas_focus._state.update(previous=[], prev_failed=[], current=[])
    assert pk.close(CLAIM[lang], {}, acted=False, brief=ORDER), "nothing put it there"
    _a_search_ran_last_turn(refused=True)
    assert canvas_focus.last_turn_held(["youtube"]) == ""
    assert pk.close(CLAIM[lang], {}, acted=False, brief=ORDER), "the card refused the op: the claimed state does not hold"
    _a_search_ran_last_turn()
    assert pk.owed(ORDER, open_ids=[]) is True, "the card it acted on is closed now"
