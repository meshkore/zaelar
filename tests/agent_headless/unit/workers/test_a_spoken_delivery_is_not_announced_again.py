"""A result spoken to him is not handed to the next turn as news (demo pass 2026-09-28).

The monitor errand finished during V3 and was SPOKEN; its «Tarea completada» note stayed queued anyway, and the
next two replies («Done, back to normal. By the way, those three monitors turned up…») announced it again — three
times in all, each one a long readout that pushed the answers to his orders a turn behind.
"""
import asyncio
from types import SimpleNamespace

import pytest

from voice import brain_notes, proactive
from nucleo.workers import session


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    brain_notes.drain()
    monkeypatch.setattr(proactive, "_wait_for_quiet", lambda *a, **k: asyncio.sleep(0, result=True))
    monkeypatch.setattr(proactive, "_BOT_GRACE_SECS", 0.0)
    import nucleo.memory_agent as ma
    monkeypatch.setattr(ma, "remember", lambda *a, **k: asyncio.sleep(0))
    yield
    brain_notes.drain()


def _rec():
    return SimpleNamespace(task_id="e7e430-2", ok=True, kind="web", goal="three monitors",
                           result_summary="Done — three 27-inch 4K monitors, all under $400: KTC $254.98…")


def test_spoken_means_the_note_is_withdrawn(monkeypatch):
    said = []

    async def speaker(text):
        said.append(text)
    monkeypatch.setattr(proactive, "_speaker", speaker)
    asyncio.run(session._deliver(_rec()))
    assert said, "it was spoken"
    assert not [n for n in brain_notes.drain() if "Tarea completada" in n], "and not queued as news as well"


def test_not_spoken_means_the_note_stays(monkeypatch):
    monkeypatch.setattr(proactive, "_speaker", None)
    asyncio.run(session._deliver(_rec()))
    assert [n for n in brain_notes.drain() if "Tarea completada" in n], "the text channel still learns it"


def test_an_interim_word_that_finds_no_quiet_moment_stays_on_screen(monkeypatch):
    """«On the monitors: a Philips… no price confirmed yet» rode his answers about Apple's chart and the music:
    a worker's interim `say` that cannot be said is not carried into the conversation."""
    monkeypatch.setattr(proactive, "_speaker", lambda t: None)
    monkeypatch.setattr(proactive, "_wait_for_quiet", lambda *a, **k: asyncio.sleep(0, result=False))
    said = asyncio.run(proactive.notify("zaelar", "On the monitors: a Philips came up", carry=False))
    assert said is False and not brain_notes.drain()
    asyncio.run(proactive.notify("zaelar", "the result", carry=True))
    assert brain_notes.drain(), "a carried delivery still degrades to a note"


def test_the_worker_say_route_does_not_carry():
    import inspect
    from nucleo import worker_api
    src = inspect.getsource(worker_api.worker_say)
    assert "carry=False" in src
