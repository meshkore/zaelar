"""A turn whose words claim a leaving act no door reached hands that act to its task (V2-851, measured 2026-11-05).

On the operator's engine «manda un mensaje a pablo diciendo hola» was read surely (`screen_action =
mensajeria:send_to` 0.98) and answered «Sending "hola" to Pablo now…» with ZERO calls: the line claimed a send that
would never happen. The class: an identified leaving act the turn did not make is an identified task — a Brain Worker
on its own row with the `message` playbook — so the start the line announced is real. A question, an unsure verdict
or an act that does not leave the machine is never routed.

Disarm: make `claimed` return 0 before it escalates and the first test goes red.
"""
from __future__ import annotations

import pytest

from nucleo.request import ask_outside_door as aod


@pytest.fixture
def wired(monkeypatch):
    seen = {"escalated": [], "patched": [], "events": []}
    from nucleo.turn import verdicts
    from widgets import effects
    from nucleo.request import model
    from nucleo.circuit import ledger
    from nucleo.acts import errand

    state = {"target": ("mensajeria:send_to", {"used": True, "confidence": 0.98}), "leaves": True}
    monkeypatch.setattr(verdicts, "read", lambda h, k, fb, min_confidence=None: state["target"]
                        if k == "screen_action" and state["target"][1]["confidence"] >= (min_confidence or 0)
                        else (fb, None))
    monkeypatch.setattr(effects, "leaves", lambda card, act: state["leaves"])
    monkeypatch.setattr(model, "opened", lambda wid, act, text="": "row-1")

    class _Store:
        def task_patch(self, uid, **kw):
            seen["patched"].append((uid, kw))
    monkeypatch.setattr(ledger, "store", lambda: _Store())
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda text, context=None: seen["escalated"].append((text, context)) or 7)
    emit = lambda *a, **k: seen["events"].append((a, k))   # noqa: E731
    return seen, state, emit


def test_a_claimed_send_with_no_call_becomes_a_message_task(wired):
    seen, _state, emit = wired
    tid = aod.claimed({}, 'Sending "hola" to Pablo now.', "manda un mensaje a pablo diciendo hola", emit=emit)
    assert tid == 7
    (text, ctx), = seen["escalated"]
    assert text == "manda un mensaje a pablo diciendo hola"
    assert ctx["task_uid"] == "row-1" and ctx["playbook"] == "message"
    assert ("row-1", {"playbook": "message"}) in seen["patched"]


def test_a_question_is_never_a_claim(wired):
    seen, _state, emit = wired
    assert aod.claimed({}, "¿A qué Pablo se lo mando?", "manda un mensaje a pablo", emit=emit) == 0
    assert not seen["escalated"]


def test_an_unsure_verdict_or_an_act_that_stays_routes_nothing(wired):
    seen, state, emit = wired
    state["target"] = ("mensajeria:send_to", {"used": True, "confidence": 0.6})
    assert aod.claimed({}, "Sending it now.", "manda un mensaje a pablo", emit=emit) == 0
    state["target"] = ("mensajeria:send_to", {"used": True, "confidence": 0.98})
    state["leaves"] = False
    assert aod.claimed({}, "Done.", "abre mensajería", emit=emit) == 0
    assert not seen["escalated"]
