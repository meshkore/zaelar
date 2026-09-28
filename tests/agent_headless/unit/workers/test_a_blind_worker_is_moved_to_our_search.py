"""A worker whose own search runs out of quota is moved to Zaelar's search (operator, 2026-09-28).

Blindness was detected and announced (`providers.note_tool_blindness`) and nothing changed for the worker: in
demo pass 30 the provider's web reader answered 429 while its model worked, and the monitors worker went on
without material. The rule: the provider's own search first while it works, OURS when its quota runs out — the
same search the FlashBrain uses, through the per-task bridge. The spawn prompt names both; on blindness the
live worker is told, once, to switch.
"""
import asyncio

import pytest

from nucleo import dispatch_prompts as DP
from nucleo.workers.base import WorkerEvent
from nucleo.workers.session import SessionRecord, WorkerSession

_BLIND = "MCP error -429: webReader usage limit reached for your plan (quota exceeded), reset at 2026-09-29 01:39"


class _Backend:
    name = "fake"

    async def start(self, prompt, *, spec):
        pass

    async def send(self, text):
        pass

    async def events(self):
        return
        yield  # pragma: no cover

    async def stop(self):
        pass


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr("voice.health_state.record", lambda *a, **k: None, raising=False)
    rec = SessionRecord(task_id="t9", goal="three 27 inch 4k monitors", kind="web")
    return WorkerSession(_Backend(), type("S", (), {"model": "", "kind": "web"})(), rec)


def _blind_step(s):
    s._on_event(WorkerEvent(task_id="t9", type="step_result",
                            data={"where": "web", "tool": "webReader", "text": _BLIND, "is_error": True}))


def test_a_blind_worker_is_told_to_use_our_search_once(session):
    async def run():
        _blind_step(session)
        _blind_step(session)
        await asyncio.sleep(0)
    asyncio.run(run())
    told = [i.text for i in session._rec.injects]
    assert len(told) == 1, told
    assert "worker_bridge act use_tool @busca.json" in told[0] and "web_search" in told[0]


def test_an_ordinary_tool_error_moves_nothing(session):
    async def run():
        session._on_event(WorkerEvent(task_id="t9", type="step_result",
                                      data={"where": "web", "tool": "WebFetch", "text": "HTTP 404 Not Found",
                                            "is_error": True}))
        await asyncio.sleep(0)
    asyncio.run(run())
    assert session._rec.injects == []


def test_the_spawn_prompt_names_both_searches_and_the_order():
    text = DP._drawer_rules("/x/py")
    assert "DOS buscadores" in text and "Primero el TUYO" in text
    assert "act use_tool @busca.json" in text
