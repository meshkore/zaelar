"""V2-152 — a worker-driven browser task left NO trace of what it had done in its own record.

`tasks.milestone()` is what fills the card feed, and the only caller in the live path was `_automate` — the
browser's OWN loop, which a Brain Worker does not use: it drives through `nav_cli` → `/api/navegador/act` →
`TaskBrowser.agent_act`. So for the whole life of a worker task `events` stayed empty, which meant
`active_progress()` reported `steps=0` and `last_event=""` no matter how much browsing had happened, and the
brain had a step COUNT of zero to answer «¿cómo va?» with.

Reaching a page is a milestone by this module's own definition (what the task DID, not every click), so that is
where the line goes — not on clicks and types, which is exactly the flood `_emit`'s docstring rejects.
"""
from __future__ import annotations

import asyncio

import pytest

from widgets.navegador import owner as O
from widgets.navegador import tasks as T


class _FakePage:
    url = "https://www.booking.com/hotel/es/palacio-de-la-merced.es.html"


@pytest.fixture
def task_and_browser(monkeypatch):
    tid = T.create(goal="reservar una noche en el Hotel Palacio de la Merced", title="hotel")
    tb = O.TaskBrowser(tid)
    tb.page = _FakePage()

    async def _ensure():
        return tb.page

    async def _goto(_url):
        return None

    monkeypatch.setattr(tb, "ensure", _ensure)
    monkeypatch.setattr(tb, "_goto", _goto)
    return tid, tb


def test_navigating_leaves_a_milestone_in_the_task_feed(task_and_browser):
    tid, tb = task_and_browser
    assert T.get(tid)["events"] == []
    ok, msg = asyncio.run(tb.agent_act("navigate", {"url": "https://www.booking.com"}))
    assert ok
    feed = T.get(tid)["events"]
    assert len(feed) == 1
    assert "booking.com" in feed[0]["text"]


def test_and_that_milestone_is_what_the_brain_gets_to_say(task_and_browser):
    """The point is not the feed for its own sake: `active_progress` is what reaches the prompt, and until now it
    could only ever report zero steps for a task a worker was driving."""
    tid, tb = task_and_browser
    asyncio.run(tb.agent_act("navigate", {"url": "https://www.booking.com"}))
    row = next((r for r in T.active_progress() if r["id"] == tid), None)
    assert row is not None
    assert row["steps"] == 1
    assert "booking.com" in row["last_event"]


def test_but_a_click_is_not_a_milestone(task_and_browser, monkeypatch):
    """`_emit`'s own rule: the feed tells the PROCESS, not every action. A line per click would drown the very
    milestone this adds."""
    tid, tb = task_and_browser

    async def _noop():
        return None

    monkeypatch.setattr(tb, "_capture", _noop)
    monkeypatch.setattr(tb, "_reap_popups", _noop)
    asyncio.run(tb.agent_act("click_at", {"x": 10, "y": 10}))
    assert T.get(tid)["events"] == []
