"""The `jev read` event is FROZEN across the brief's move (refactor2710-07, V2-826 §2b).

Every reader of a verdict leaves one `jev read <question>` row in the timeline — the observatory and the Master filter
on its kind, label and `extra` keys. 07 moved the reading door (`nucleo/turn/verdicts.read` over `nucleo/jev`), so this
pins the row the old `jev.read` emitted: same kind, same label, same text, same extra, one per (call, question).

Disarm: rename the label in `nucleo/jev._emit_read` and the frozen-shape test goes red.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import jev
from nucleo.turn import brief, verdicts

FROZEN_EXTRA = {"cat", "call_id", "turn_id", "question", "used", "why", "confidence", "choice"}


@pytest.fixture
def events(monkeypatch):
    got = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: got.append((kind, label, kw)))
    jev.reset_read_events()
    yield got
    jev.reset_read_events()


def _handle(choice, conf, call_id="C1"):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "T1", "_call_id": call_id,
            "result": {brief.REQUEST_KEY: {"choice": choice, "confidence": conf}}}


def test_a_used_verdict_leaves_the_frozen_row(events):
    assert verdicts.read(_handle("order", 0.9), brief.REQUEST_KEY, "")[0] == "order"
    (kind, label, kw), = events
    assert (kind, label, kw["role"]) == ("brain", f"jev read {brief.REQUEST_KEY}", "system")
    assert kw["text"] == "order -> USED (0.90)"
    assert set(kw["extra"]) == FROZEN_EXTRA
    assert kw["extra"] | {} == {"cat": "flash", "call_id": "C1", "turn_id": "T1", "question": brief.REQUEST_KEY,
                                "used": True, "why": "used", "confidence": 0.9, "choice": "order"}


def test_an_unsure_verdict_says_why_and_one_row_per_call_and_question(events):
    h = _handle("order", 0.3, call_id="C2")
    assert verdicts.read(h, brief.REQUEST_KEY, "fb")[0] == "fb"
    verdicts.read(h, brief.REQUEST_KEY, "fb")
    brief.read(h, brief.REQUEST_KEY, "fb")
    assert len(events) == 1, "deduped on (call, question): a reader in a loop never floods the timeline"
    kind, label, kw = events[0]
    assert label == f"jev read {brief.REQUEST_KEY}" and kw["extra"]["used"] is False
    assert kw["text"].startswith("order -> ") and kw["extra"]["why"] != "used"
