"""V2-778 F0-4 — a data-op that did not run is SAID, and «Done.» never stands over it.

Two silent exits, found by the 2026-09-30 self-audit:

  · the turn started the op with `_spawn(dispatch_and_report(...))` under `except: pass` — when building the call
    raised, the op never ran, `data_done` stayed True (so the ack backstop said «Done.») and nothing was logged;
  · inside `dispatch_and_report`, a widget dispatch that RAISED returned None: no row settled, no seal, no word.

Both now go through `data_ops._say_it_did_not_run`: a `brain` failure event, the row settled `unmet`, the seal told
it did not happen, and `report_failure` with the language's own `op_failed` line — spoken, not a bare `error`.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

import asyncio
import re
from pathlib import Path

from nucleo.flash import data_ops

PROVIDER = Path(__file__).resolve().parents[3] / "voice" / "engine" / "llm" / "providers" / "nucleo.py"


def _capture(monkeypatch):
    events, reported = [], []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **k: events.append((a, k)))

    async def _report(wid, action, res):
        reported.append((wid, action, res))
        return True
    monkeypatch.setattr(data_ops, "report_failure", _report)
    return events, reported


def test_an_op_whose_call_cannot_be_built_is_reported_and_not_returned(monkeypatch):
    events, reported = _capture(monkeypatch)
    sealed, spawned = [], []

    def _spawn(coro, label):
        spawned.append(label)
        asyncio.run(coro)
        return "task"

    def _boom():
        raise RuntimeError("the turn's half could not be built")

    got = data_ops.start_op("agenda", "add", {}, seal=sealed.append, text=_boom, said="", spawn=_spawn)
    assert got is None, "an op that never started must not look like a running task"
    assert spawned == ["widget-data-failed"]
    assert sealed == [False], "the anti-drag memory must not remember it as done"
    assert reported and reported[0][2]["ok"] is False and reported[0][2]["message"], \
        "the failure is reported with a SPEAKABLE message, not only an internal error"
    assert any("no se ejecutó" in str(a) for a, _ in events)


def test_a_dispatch_that_raises_is_said(monkeypatch):
    events, reported = _capture(monkeypatch)
    import widgets

    async def _raise(*a, **k):
        raise ConnectionError("widget process gone")
    monkeypatch.setattr(widgets, "dispatch_tag", _raise)
    sealed = []
    res = asyncio.run(data_ops.dispatch_and_report("agenda", "add", {"title": "x"}, seal=sealed.append))
    assert isinstance(res, dict) and res.get("ok") is False, "a raised dispatch returns a refusal, not None"
    assert sealed == [False]
    assert reported, "and it reaches the operator"


def test_the_turn_forgets_an_op_that_did_not_start():
    """SOURCE guard over the voice turn (provider + its tool executor, `tests/voice_turn_source.py`)."""
    src = _vts.read(PROVIDER)
    m = re.search(r"_op_task = _data_ops\.start_op\((.*?)\n\s+# An action whose output only exists ON SCREEN", src, re.S)
    assert m, "the turn no longer starts its data-op through `start_op`"
    block = m.group(1)
    assert "if _op_task is not None" in block and 'data_done["v"] = bool(' in block, \
        "an op that did not start must be taken back out of `data_done`, or «Done.» is said over it"
    assert "except Exception:\n                    pass" not in block
