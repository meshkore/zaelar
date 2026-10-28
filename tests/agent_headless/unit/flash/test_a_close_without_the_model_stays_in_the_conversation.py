"""A turn answered without the model stays in the conversation (V2-831 T-02, class 2).

Measured 2026-10-28, typed, EN: «close all» → hard interrupt, receipt «I've closed Messages, Results and Browser. Still
on screen: Document.» → «i said all» → a model turn whose window held neither line, so it read «all» as «tell me all»
about the previous errand. The hard close now writes his line and our receipt into the dialog window (and
`_last_reply`, what the next brief is handed as what we just said), like a model turn — so a repair has something to
repair.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import done_ops
from nucleo.flash import bulk_close, dialog, hard_turn

OPEN = ["documento", "navegador", "mensajeria"]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    done_ops.reset()
    bulk_close.reset()
    from nucleo.acts import canvas_turn
    monkeypatch.setattr(canvas_turn, "request_of", lambda brief=None, text=None, **k: {
        "text": text or "", "turn_credit": True, "last_reply": "", "verdict": {"canvas": ("close", 0.9)}})
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: list(OPEN))
    from memory import api as memory
    monkeypatch.setattr(memory, "write", lambda *a, **k: None)
    done_ops.note("documento", "show", {"body": "draft"})      # the Document is the card in use
    yield
    done_ops.reset()
    bulk_close.reset()


def _collect():
    events: list[tuple] = []

    def emit(kind, action, text=None, role=None, extra=None):
        events.append((kind, action, text, dict(extra or {})))
    return events, emit


def _closed(events) -> list:
    return [e[3].get("id", "*ALL*") for e in events if e[0] == "widget" and e[1] == "close"]


class _Brain:
    def __init__(self):
        self._window = [{"role": "user", "content": "continue with my dexter request"},
                        {"role": "assistant", "content": "On it — checking where Season 2 streams."}]
        self._last_reply = "On it — checking where Season 2 streams."
        self._last_spoken = ""
        self._last_spoke_at = 0.0


# ── class 2 ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _spoken(monkeypatch, live=True):
    from voice import proactive
    said: list[str] = []
    monkeypatch.setattr(proactive, "speaker", (lambda: said.append) if live else (lambda: None))
    monkeypatch.setattr(proactive, "user_speaking", lambda: False)
    return said


@pytest.mark.parametrize("live", [True, False], ids=["spoken", "chat-only"])
def test_a_hard_close_leaves_his_line_and_our_receipt_in_the_window(monkeypatch, live):
    monkeypatch.setattr(bulk_close, "_open_instances", lambda: ["navegador", "mensajeria"])
    _spoken(monkeypatch, live)
    brain, (events, emit) = _Brain(), _collect()
    asyncio.run(hard_turn.handle("close all", "close", emit, brain))
    receipt = next(e[2] for e in events if e[1] == "🧾 close receipt")
    assert brain._window[-2:] == [{"role": "user", "content": "close all"},
                                  {"role": "assistant", "content": receipt}]
    assert brain._last_reply == receipt


def test_the_repair_turn_reads_the_close_as_what_we_just_said(monkeypatch):
    """«i said all» — the next turn's window ends in the close, and the line its brief is handed as what we just said
    (`last_reply`, `prior_line`) is the receipt, not the previous errand."""
    from nucleo.flash import prior_line
    from nucleo.turn import brief
    _spoken(monkeypatch)
    brain, (events, emit) = _Brain(), _collect()
    asyncio.run(hard_turn.handle("Close all.", "close", emit, brain))
    receipt = brain._window[-1]["content"]
    dialog.push_user(brain._window, "i said all")
    assert [m["content"] for m in brain._window[-3:]] == ["Close all.", receipt, "i said all"]
    assert prior_line.snapshot(brain, brain._window[:-1]) == receipt
    assert receipt in brief.request_question(brain._last_reply)["instructions"]


def test_the_window_stays_capped(monkeypatch):
    _spoken(monkeypatch)
    brain, (events, emit) = _Brain(), _collect()
    brain._window = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"line {i}"} for i in range(10)]
    asyncio.run(hard_turn.handle("close all", "close", emit, brain))
    assert len(brain._window) == 10 and brain._window[-2]["content"] == "close all"


def test_with_no_receipt_the_engine_ack_closes_the_order():
    brain = _Brain()
    dialog.record_turn_without_model(brain, "close all", "")
    win = brain._window
    assert win[-2]["content"] == "close all" and win[-1]["role"] == "assistant" and win[-1]["content"]
    assert brain._last_reply == win[-1]["content"]


def test_disarmed_without_the_record_the_close_never_happened(monkeypatch):
    """RED proof: skip the record and the window still ends in the Dexter errand — what T12 read."""
    _spoken(monkeypatch)
    real = dialog.record_turn_without_model
    dialog.record_turn_without_model = lambda brain, said, reply, cap=10: None
    try:
        brain, (events, emit) = _Brain(), _collect()
        asyncio.run(hard_turn.handle("close all", "close", emit, brain))
        assert brain._window[-2]["content"] == "continue with my dexter request", "the disarm did not land"
    finally:
        dialog.record_turn_without_model = real
    bulk_close.reset()
    brain, (events, emit) = _Brain(), _collect()
    asyncio.run(hard_turn.handle("close all", "close", emit, brain))
    assert brain._window[-2]["content"] == "close all"                   # green again
