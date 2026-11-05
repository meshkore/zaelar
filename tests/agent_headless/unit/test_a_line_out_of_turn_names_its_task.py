"""A line said outside a turn goes through ONE door and names what it belongs to (V2-851 F2, node 2.1070).

The out-of-turn mouth is `nucleo/pulse/notices.notify`: a line about a task carries the task's id, a line about
nothing (an inbound message, a sign-in left halfway) carries a notice key, and the same line about the same task
never reaches him twice. The battery's line reader (`tests/agent_headless/e2e/task_battery/probe.line_source`) reads
those two fields off the line's event: without them a task's line is an anonymous 🔔 nobody can attribute.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo import runstate
from nucleo.pulse import notices


@pytest.fixture
def events(monkeypatch):
    got = []
    monkeypatch.setattr("voice.observer.emit", lambda kind, label, **kw: got.append((kind, label, kw.get("extra") or {})))
    monkeypatch.setattr(runstate, "stopped", lambda: False)
    monkeypatch.setattr(notices, "push", lambda row: 0)
    monkeypatch.setattr(notices, "someone_looking", lambda now=None: True)
    return got


def _lines(got):
    from tests.agent_headless.e2e.task_battery import probe
    out = []
    for kind, label, extra in got:
        ev = {"kind": kind, "label": label, "payload": {**extra, "extra": extra}}
        src = probe.line_source(ev)
        if src:
            out.append((src, extra))
    return out


def test_a_task_line_carries_its_task_id_and_is_said_once(events):
    a = asyncio.run(notices.notify("zaelar", "Your list is done: 3 of 3.", task_id="boot-i7", kind="done"))
    b = asyncio.run(notices.notify("zaelar", "Your list is done: 3 of 3.", task_id="boot-i7", kind="done"))
    lines = _lines(events)
    assert [src for src, _ in lines] == ["say"], f"one line, read as the task's own: {lines}"
    assert lines[0][1]["task_id"] == "boot-i7"
    assert b["duplicate"] and not a["duplicate"], "the same line about the same task never reaches him twice"
    assert notices.get(a["id"])["detail"]["task_id"] == "boot-i7", "the ledger row names the task"


def test_a_new_line_about_the_same_task_is_said(events):
    asyncio.run(notices.notify("zaelar", "Sign in in the window.", task_id="nav-3"))
    r = asyncio.run(notices.notify("zaelar", "Session saved, carrying on.", task_id="nav-3"))
    assert not r["duplicate"] and len(_lines(events)) == 2


def test_a_notice_without_a_task_carries_its_key(events):
    asyncio.run(notices.notify("Telegram", "2 new messages on Telegram from Rowan", key="msg:telegram:42"))
    lines = _lines(events)
    assert [src for src, _ in lines] == ["notice"] and lines[0][1]["key"] == "msg:telegram:42"
    ledger = [e for k, _l, e in events if k == "notice"]
    assert ledger and ledger[-1]["key"] == "msg:telegram:42", "the ledger's own event names the notice too"


def test_a_line_painted_on_the_screen_he_is_at_is_shown_not_owed(events, monkeypatch):
    from voice import proactive

    async def unsaid(title, text, **kw):
        return False
    monkeypatch.setattr(proactive, "notify", unsaid)
    r = asyncio.run(notices.notify("zaelar", "Still building the card.", task_id="w-1", push_=False))
    assert r["state"] == "shown", "voice if quiet, else the screen: a line on his screen is not owed to the next one"
