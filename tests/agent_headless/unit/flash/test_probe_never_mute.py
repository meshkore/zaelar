"""nucleo/flash/probe.py::run_turn — a plain chat turn that comes back with no tool call and no text must not
stay mute (2026-08-17, live bug found running tests/use_cases' dynamic harness against `search-buy-used-car`):
after several worker check-ins ("¿pudiste relanzarla?"), the FlashBrain gave one completely silent turn; the
NEXT turn, seeing that gap in the conversation window, ended up echoing the operator's own question back
verbatim ("Dime algo, por favor. ¿Se relanzó la búsqueda...?" — literally the tester's own words). None of the
existing "never mudo" backstops in `run_turn` are gated on `action=="chat"` (they only cover widget_data/
canvas/escalate/music/style), so a genuinely empty chat reply fell through all of them. Mirrors the identical
fix in `voice/engine/llm/providers/nucleo.py` (the real voice provider) — impl PARALELA, not independently unit
tested there (that function has no harness for a full turn yet, see V2-112/V2-098).
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from voice import brain_notes


class _MuteFastClient:
    """Stub: the model streams nothing and calls no tool — a genuinely mute turn, no exception either."""

    async def stream(self, *_a, **_kw):
        return
        yield  # pragma: no cover — never reached; keeps this an async generator


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def probe_session():
    sid = "test-never-mute"
    brain_notes.drain()
    yield sid
    probe._SESSIONS.pop(sid, None)
    brain_notes.drain()


def test_mute_chat_turn_with_worker_active_falls_back_to_still_working_filler(
        fresh_db, probe_session, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _MuteFastClient)
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: True)

    question = "¿Va todo bien? ¿Pudiste relanzar la búsqueda o sigue atascada? Dime algo."
    res = asyncio.run(probe.run_turn(question, sid=probe_session, ingest=False))

    assert res["ok"] is True
    assert res["action"] == "chat"
    assert res["reply"]                    # never mute
    assert res["reply"] != question        # never a verbatim echo of what the operator just said


def test_mute_chat_turn_with_nothing_running_asks_to_repeat(fresh_db, probe_session, monkeypatch):
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _MuteFastClient)
    monkeypatch.setattr("nucleo.dispatch.has_active", lambda: False)

    res = asyncio.run(probe.run_turn("hola", sid=probe_session, ingest=False))

    assert res["ok"] is True
    assert res["reply"]
