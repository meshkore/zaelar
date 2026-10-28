"""The search browser's context serves only the event loop that made it (refactor2710-01 sweep).

`demo-b1-wallpaper…` timed out at 60 s on two of three typed turns: each bank turn runs in its own `asyncio.run`, the
first image search started the persistent Chromium context — and its start lock — on that loop, and the next turn
awaited both from a new loop, waiting for a loop that was gone. A process-wide async resource is bound to its loop:
from another one it is started again, never awaited.

Disarm: drop the owner check in `search.browser.ensure_started` → the second run reuses the first loop's context.
"""
from __future__ import annotations

import asyncio
import sys
import types

import pytest

from search import browser


class _Ctx:
    def __init__(self, loop):
        self.loop = loop

    def set_default_timeout(self, _ms):
        pass

    async def new_page(self):
        raise RuntimeError("no network in a unit test")   # the warm visit is best-effort


@pytest.fixture
def fake_playwright(monkeypatch):
    started: list = []

    class _Chromium:
        async def launch_persistent_context(self, *_a, **_k):
            ctx = _Ctx(asyncio.get_running_loop())
            started.append(ctx)
            return ctx

    class _PW:
        chromium = _Chromium()

    class _Starter:
        async def start(self):
            return _PW()

    mod = types.ModuleType("playwright.async_api")
    mod.async_playwright = lambda: _Starter()
    monkeypatch.setitem(sys.modules, "playwright.async_api", mod)
    monkeypatch.setenv("BROWSER_SEARCH", "1")
    for name in ("_pw", "_ctx", "_start_lock", "_owner"):
        monkeypatch.setattr(browser, name, None)
    return started


def test_a_second_loop_starts_its_own_context(fake_playwright):
    assert asyncio.run(browser.ensure_started()) is True
    assert asyncio.run(browser.ensure_started()) is True
    assert len(fake_playwright) == 2, "the second loop reused a context bound to the first one"
    assert fake_playwright[0].loop is not fake_playwright[1].loop


def test_the_same_loop_keeps_its_context(fake_playwright):
    async def twice():
        return await browser.ensure_started(), await browser.ensure_started()
    assert asyncio.run(twice()) == (True, True)
    assert len(fake_playwright) == 1
