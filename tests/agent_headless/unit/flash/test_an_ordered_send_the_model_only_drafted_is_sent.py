"""An ORDERED act that leaves runs when the model only prepared it (2026-10-15, the operator's 70%).

Live bench E3: «send the invoice to quinn, tell him we're already trying inworld and he should book it» — order at
1.00, `mensajeria:forward` at 0.79, and the model called `draft`: 2 of 7 runs sent nothing and said «Done.». The
mirror of the voice rule that runs the verdict over a model call that LEAVES when nobody asked for it.

Disarm: return None from `ordered_send.instead` → red; unwire it from `verdict_card.retarget` → the wiring test red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import ordered_send

SAID = "send the invoice to quinn, tell him we're already trying inworld and he should book it"


def _brief(target: str, conf: float, kind: str = "order") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {"screen_action": {"choice": target, "confidence": conf},
                       "request_type": {"choice": kind, "confidence": 1.0}}}


@pytest.fixture(autouse=True)
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    import server.voice_api as _va
    monkeypatch.setattr(_va, "open_instances", lambda: ["mensajeria"])


def test_a_draft_under_a_sure_ordered_forward_becomes_the_forward():
    got = ordered_send.instead(_brief("mensajeria:forward", 0.79), "mensajeria", "draft",
                               {"text": "We're already trying Inworld — please book it."}, SAID)
    assert got and got[0] == "forward", got
    assert got[1].get("text", "").startswith("We're already trying Inworld") and got[1].get("contact"), got


def test_under_the_bar_or_a_model_that_sends_or_a_question_nothing_changes():
    draft = {"text": "book it"}
    assert ordered_send.instead(_brief("mensajeria:forward", 0.6), "mensajeria", "draft", draft, SAID) is None
    assert ordered_send.instead(_brief("mensajeria:forward", 0.9), "mensajeria", "send_to", draft, SAID) is None
    assert ordered_send.instead(_brief("mensajeria:forward", 0.9, kind="question"), "mensajeria", "draft", draft, SAID) is None
    assert ordered_send.instead(_brief("mensajeria:forward", 0.9), "mensajeria", "forward", draft, SAID) is None


def test_both_channels_ask_it():
    import inspect
    from nucleo.flash import tool_executor_widget_calls, verdict_card
    assert "_os.instead(brief, widget_id, action, payload, said)" in inspect.getsource(verdict_card.retarget)
    assert "_txw._ordered_send.run(_brief, wid, action_name, payload" in inspect.getsource(tool_executor_widget_calls)


def test_a_dry_turn_reports_the_call_as_it_would_run():
    """The bank and the live bench run dry; their report must carry the engine's own resolution, or they measure the
    model's raw call and stay blind to this rule. Run through the typed turn (the voice turn, dry)."""
    from tests.brain import harness as H
    case = {"id": "ordered-send-dry", "lang": "en", "phrase": SAID, "source": "live bench E3",
            "screen": {"open": ["mensajeria"]}, "expect": "data-op mensajeria:forward",
            "widgets": {"contactos": {"contacts": [{"name": "Quinn", "email": "quinn@example.com"}]}},
            "model": {"say": "", "tools": [{"name": "widget_data", "args": {
                "widget_id": "mensajeria", "action": "draft", "payload": {"text": "please book it"}}}]},
            "brief": {"screen_action": ["mensajeria:forward", 0.79], "request_type": ["order", 1.0]}}
    out = H.run_case(case)
    assert not out.error, out.error
    assert out.decision == "data-op mensajeria:forward", (out.decision, out.tool_calls, out.reply)
