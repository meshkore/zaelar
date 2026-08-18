"""V2-135 (`quick-fact-opening-hours`) — the composing pass saw the QUERY as the question, and the query is the
model's own reformulation.

«¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?» is two facts in one sentence.
If the model searches «horario Museo del Prado», the second pass — the one that turns results into a spoken
answer — used to receive `PREGUNTA: horario Museo del Prado`, with the operator's real sentence nowhere in it.
The price half was gone BEFORE composition: not the model choosing to skip it, the half no longer existing.

That is the same shape in both channels, so it was never a probe/provider divergence — it was a shared design
flaw, and it is the «half a request lost» class the operator ranks third in severity.

Now the pass carries both: what the operator ASKED, verbatim, and what was actually SEARCHED. The difference
between the two is precisely what lets the reply say which half the results do not cover instead of dropping it
in silence.
"""
from __future__ import annotations

import asyncio

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from nucleo.flash import probe
from nucleo.flash import prompt


QUESTION = "¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?"
HALF_QUERY = "horario Museo del Prado"


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
def captured(monkeypatch):
    """Drives a real `run_turn`: first pass calls web_search with HALF the question, second pass is captured."""
    seen: dict = {}
    calls = {"n": 0}

    class _Client:
        async def stream(self, messages, *_a, on_tool_call=None, **_kw):
            calls["n"] += 1
            if calls["n"] == 1:
                if on_tool_call is not None:
                    res = on_tool_call("web_search", {"query": HALF_QUERY})
                    if asyncio.iscoroutine(res):
                        await res
                return
                yield  # pragma: no cover — keeps this an async generator
            seen["system"] = messages[0]["content"]
            seen["user"] = messages[1]["content"]
            yield "Abre a las 10:00; del precio no he encontrado nada, ¿lo miro a fondo?"

    import nucleo.websearch as ws
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", _Client)
    monkeypatch.setattr(ws, "search", lambda q, **k: {"source": "test", "ai": False, "results": [], "answer": ""})
    monkeypatch.setattr(ws, "format_results", lambda r: "(sin resultados)")
    return seen


def test_the_composing_pass_gets_what_the_operator_actually_asked(fresh_db, captured):
    res = asyncio.run(probe.run_turn(QUESTION, sid="t-v135-a", ingest=False))
    probe._SESSIONS.pop("t-v135-a", None)
    assert res["action"] == "search"
    assert captured["user"] == QUESTION                 # the whole sentence, not the query
    assert "cuánto cuesta" in captured["system"]        # the half the query dropped is still there


def test_and_it_also_gets_what_was_actually_searched(fresh_db, captured):
    """Both are needed: without the query the reply cannot tell which half the results even cover."""
    asyncio.run(probe.run_turn(QUESTION, sid="t-v135-b", ingest=False))
    probe._SESSIONS.pop("t-v135-b", None)
    assert HALF_QUERY in captured["system"]


def test_the_missing_half_must_be_named_not_dropped(fresh_db, captured):
    asyncio.run(probe.run_turn(QUESTION, sid="t-v135-c", ingest=False))
    probe._SESSIONS.pop("t-v135-c", None)
    assert "di CUÁL falta" in captured["system"]
    assert "no la dejes caer en silencio" in captured["system"]


def test_the_first_pass_is_told_the_query_must_cover_both(fresh_db):
    """Answering both halves starts at the SEARCH: with half a query there is nothing to answer the other half
    with, and that is not the model forgetting."""
    system, _ = prompt.build_flash_system()
    assert "que la BÚSQUEDA cubra las dos" in system
    assert "las contestas LAS DOS en ese turno" in system     # the V2-120 rule this extends
