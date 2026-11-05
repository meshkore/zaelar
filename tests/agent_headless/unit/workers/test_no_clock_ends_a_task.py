"""V2-852 T06 · No time budget ends a task (the operator's rule R2).

Measured in his session of 2026-11-05: at 15 minutes the pulse asked «running for 15 minutes… stop or keep going?»,
he answered «Proceed and continue», and at 36 minutes the pulse cancelled the task anyway, «it ran out of time». A task
ends on its `done_when` met, on his stop, or on a hard failure with its reason — its age is never a cause, and nothing
asks him whether to keep going.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

from nucleo import dispatch


def _pulse(monkeypatch, age_s: int):
    from nucleo.pulse import loop as _loop, workers as _workers
    seen = {"cancel": [], "said": [], "inject": [], "topics": []}
    rows = [{"id": "19", "status": "running", "kind": "research", "age_s": age_s, "silent_s": 0,
             "unreported_s": 0, "backend": "claude_code", "title": "Mercedes GLC search"}]

    async def _inject(text):
        seen["inject"].append(text)

    rec = SimpleNamespace(session=SimpleNamespace(inject=_inject), done_when={}, task_id="19")
    monkeypatch.setattr(dispatch, "active_sessions", lambda: rows)
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec)
    monkeypatch.setattr(dispatch, "cancel_session", lambda tid, **k: seen["cancel"].append((tid, k)) or True)
    monkeypatch.setattr(dispatch, "session_alive", lambda tid: None)
    monkeypatch.setattr(_workers, "_emit", lambda topic, payload=None: seen["topics"].append(topic))
    monkeypatch.setattr(_workers, "_row_beat", lambda s, now: None)

    async def _deliver(title, text, **k):
        seen["said"].append(text)

    lp = _loop.OrchestratorLoop(deliver=_deliver)
    lp._last_reconcile = time.time()                   # the orphan sweep is another test's subject
    lp._next_relay = lambda *a, **k: None               # a relayed question is another test's subject
    return lp, seen


def test_a_task_running_for_hours_is_neither_asked_about_nor_cancelled(monkeypatch):
    for age in (15 * 60, 36 * 60, 6 * 3600):
        lp, seen = _pulse(monkeypatch, age)
        asyncio.run(lp._supervise_workers(time.time()))
        assert seen["cancel"] == [], f"a task {age // 60} min old was cancelled by its age: {seen['cancel']}"
        assert seen["inject"] == [], f"a task {age // 60} min old was told to wrap up: {seen['inject']}"
        assert seen["said"] == [], f"a task {age // 60} min old made the pulse speak: {seen['said']}"
        assert not any("budget" in t or "timeout" in t for t in seen["topics"]), seen["topics"]


def test_the_supervisor_has_no_clock_to_read():
    """The mechanism is deleted, not switched off: no budget, no «N minutes» question left to configure."""
    from nucleo.pulse.loop import OrchestratorLoop
    from i18n import langspec
    lp = OrchestratorLoop()
    for gone in ("_budget_for", "_max_secs", "_budget_secs", "_budget_grace", "_kind_budget_default"):
        assert not hasattr(lp, gone), f"the supervisor still carries {gone}"
    fields = set(getattr(langspec.LangSpec, "__dataclass_fields__", {}) or vars(langspec.LangSpec))
    assert not {"worker_budget_killed", "worker_timeout_running"} & fields
