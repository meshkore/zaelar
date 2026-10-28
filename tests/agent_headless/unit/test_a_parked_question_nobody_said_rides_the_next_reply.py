"""A parked errand's question that nobody SAID rides the next reply (three-tasks-at-once EN, 2026-10-15).

The game was parked on «If I've got this right, you're asking me to BUILD you a new card…». With no live speaker the
gate's question fell back to a note for the model, and the reply that should carry it said only the car report's
refinement. He never heard it, so «make that one jump higher» went to the car report. Now the gate records whether
the question was spoken; one that was not rides the next reply once — unless that reply already names the errand.
"""
from types import SimpleNamespace

import pytest

from nucleo.dispatch import confirm as DC

GAME = "Build a small playable platform game widget, Super Mario style, with jumping"


@pytest.fixture(autouse=True)
def clean():
    DC._PENDING_CONFIRM.clear()
    DC._SPOKEN.clear()
    yield
    DC._PENDING_CONFIRM.clear()
    DC._SPOKEN.clear()


def _park(spoken: bool):
    DC._SPOKEN["t1"] = spoken
    DC.remember_code_change("t1", GAME, SimpleNamespace(kind="code", trusted=True, context={}))
    return DC._PENDING_CONFIRM["t1"]["question"]


def test_an_unsaid_question_rides_the_next_reply_once():
    q = _park(spoken=False)
    assert DC.owed_question("Got it — pure electrics only on the car report.") == q
    assert DC.owed_question("Done.") == "", "said once, never nagged"


def test_a_question_that_was_spoken_is_not_repeated():
    _park(spoken=True)
    assert DC.owed_question("Got it — pure electrics only on the car report.") == ""


def test_a_reply_that_names_the_errand_already_carries_it():
    _park(spoken=False)
    assert DC.owed_question("Want me to build the platform game widget first?") == ""
    assert DC.owed_question("Done.") == ""


def test_the_text_channel_appends_it():
    from nucleo.flash import probe_after as PA
    q = _park(spoken=False)
    out = PA._true_to_the_gate("Got it — pure electrics only.", "send_to_worker", {}, SimpleNamespace(window=[]))
    assert out == f"Got it — pure electrics only. {q}"
