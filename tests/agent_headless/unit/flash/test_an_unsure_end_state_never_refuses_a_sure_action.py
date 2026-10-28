"""An unsure end state never refuses a SURE action verdict (refactor2710-99, the asymmetric read in any language).

Bank `msg-es-more-chats` («Enséñame más chats de WhatsApp», 7 → 1): the brief read `screen_action
mensajeria:chats_more` at 1.00 and `end_state mensajeria:empty` at 0.72. The model called `show_view`; the verdict
should have completed it with `chats_more`, but the completion gate (`spec.gate_completion`) refused it because
`chats_more` does not attest the end state — an end state read at the LICENCE bar (0.5), acting as a VETO (0.85).
The English twin held only because the model picked `chats_more` itself.

Refusing a completion is a veto, so an end state below the veto bar cannot refuse a sure action verdict. When the
action verdict is itself unsure, the gate keeps its B2 role (pass 60: «set the first one as my background» was not
completed as `results:choose`), and a SURE end state still refuses an action that does not attest it.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.circuit import spec as _spec
from nucleo.turn import brief as _tb


def _brief(action: str, a_conf: float, end: str, e_conf: float, open_ids=("mensajeria",)):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids),
            "result": {_tb.TARGET_KEY: {"choice": action, "confidence": a_conf},
                       _spec.END_KEY: {"choice": end, "confidence": e_conf}}}


@pytest.mark.parametrize("e_conf", [0.55, 0.72, 0.84])
def test_a_sure_action_is_not_refused_by_an_unsure_end_state(e_conf):
    brief = _brief("mensajeria:chats_more", 1.0, "mensajeria:empty", e_conf)
    assert _spec.gate_completion(brief, "mensajeria", "chats_more") == ""


def test_a_sure_end_state_still_refuses_an_action_that_does_not_attest_it():
    brief = _brief("mensajeria:chats_more", 1.0, "mensajeria:empty", 0.9)
    assert _spec.gate_completion(brief, "mensajeria", "chats_more"), "a sure end state is a real objection"


def test_an_unsure_action_keeps_the_end_state_gate():
    """B2's shape: the action verdict below the veto bar is still held to the end state the brief named."""
    brief = _brief("mensajeria:chats_more", 0.7, "mensajeria:empty", 0.72)
    assert _spec.gate_completion(brief, "mensajeria", "chats_more")


def test_the_completion_rung_completes_the_sure_verdict():
    """At the door the model's turn reaches: the rung resolves the sure `chats_more` instead of returning nothing."""
    from nucleo.flash import direct_action
    brief = _brief("mensajeria:chats_more", 1.0, "mensajeria:empty", 0.72)
    got = direct_action.resolve("Enséñame más chats de WhatsApp", brief=brief,
                                operator_text="Enséñame más chats de WhatsApp")
    assert (got.get("widget"), got.get("action")) == ("mensajeria", "chats_more"), got
