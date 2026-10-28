"""A «yes» answers the question WE asked before his turn — not the reply we are streaming (demo, 2026-10-22).

Two yeses were lost in one session. «Want me to start the trip plan again properly?» → «Yes»: the fragment guard
read `brain._last_reply`, already overwritten by the reply being streamed («I'm on it…», no question), and
annulled the escalation. «…running for 15 minutes now. Want me to stop it or keep going?» (said on our own) →
«Yes, please»: the stop guard looked only at his words and refused the stop as context-bleed.
"""
from __future__ import annotations

import pathlib
import threading
from types import SimpleNamespace

from nucleo.flash import dialog, escalation_guard as _eg, prior_line, turn_brief as _tb
from nucleo.flash import tool_executor_calls as _calls

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
OFFER = "Okay… the trip plan didn't actually run. Want me to start the trip plan again properly?"
STREAMING = "I'm on it — a fresh five-day plan for you and Anna, warm weather in late December."
TIMEOUT_Q = "The «monitors» process has been running for 15 minutes now. Want me to stop it or keep going?"


def _brief(kind: str):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [],
            "result": {_tb.REQUEST_KEY: {"choice": kind, "confidence": 0.99}}}


def test_the_snapshot_is_the_line_before_his_turn_and_the_stream_does_not_move_it():
    brain = SimpleNamespace(_last_reply=OFFER)
    window = [{"role": "user", "content": "you closed the document"}, {"role": "assistant", "content": OFFER}]
    assert prior_line.snapshot(brain, window) == OFFER
    brain._last_reply = STREAMING                      # what the provider does on every streamed chunk
    assert prior_line.of(brain) == OFFER


def test_a_line_we_said_on_our_own_is_what_he_answers():
    """The timeout question goes out through `proactive.notify` → `dialog.note_spoken`, never `_last_reply`."""
    dialog.note_spoken(TIMEOUT_Q)
    window = [{"role": "assistant", "content": "Here are the monitors."}]
    dialog.drain_spoken(window)
    brain = SimpleNamespace(_last_reply="Here are the monitors.")
    assert prior_line.snapshot(brain, window) == TIMEOUT_Q


def test_the_yes_to_our_offer_keeps_the_commission():
    brain = SimpleNamespace(_last_reply=OFFER)
    prior_line.snapshot(brain, [{"role": "assistant", "content": OFFER}])
    brain._last_reply = STREAMING
    req = {"v": "Build a full 5-day warm-weather vacation plan", "more": []}
    dropped = _eg.drop_if_fragment(req, operator_text="Yes", brief=_brief("answer"),
                                   last_reply=prior_line.of(brain))
    assert not dropped and req["v"], "the trip was annulled as a fragment — the guard read the streaming reply"


def _stop(text: str, *, brief, prior: str, monkeypatch) -> list:
    from nucleo import dispatch
    killed: list = []
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: killed.append(w) or ["1"])
    acted = {"v": None}
    _calls._t_stop_worker(args={"which": "the 27-inch 4K monitor search"}, _norm_nfkd=lambda s: s.lower(),
                          _say=lambda: SimpleNamespace(stop_which_worker="which?"),
                          _says_stop=lambda t: False, clarify={}, emit=lambda *a, **k: None, text=text,
                          worker_acted=acted, brief=brief, prior=prior)
    return killed


def test_a_yes_to_our_stop_question_stops_it(monkeypatch):
    assert _stop("Yes, please. I did close.", brief=_brief("answer"), prior=TIMEOUT_Q,
                 monkeypatch=monkeypatch) == ["the 27-inch 4K monitor search"]


def test_without_our_question_the_context_bleed_guard_still_holds(monkeypatch):
    assert _stop("Yes, please. I did close.", brief=_brief("answer"), prior="Here are the monitors.",
                 monkeypatch=monkeypatch) == []
    assert _stop("the monitors are ugly", brief=_brief("complaint"), prior=TIMEOUT_Q,
                 monkeypatch=monkeypatch) == []


def test_no_guard_that_runs_after_the_stream_reads_the_live_reply():
    """The wiring: the three readers take the snapshot, and the prompt builder takes it."""
    for rel in ("nucleo/flash/post_stream_acts.py", "nucleo/flash/tool_executor_calls.py",
                "nucleo/flash/tool_executor_widget_calls.py"):
        src = (_ENGINE / rel).read_text(encoding="utf-8")
        assert "_last_reply" not in src, f"{rel} reads the reply being streamed as «what we said before»"
    tp = (_ENGINE / "voice/engine/llm/providers/turn_prompt.py").read_text(encoding="utf-8")
    assert "_prior_line.snapshot(brain, brain._window)" in tp
