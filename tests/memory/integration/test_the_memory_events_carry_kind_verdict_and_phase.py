"""The memory's events say WHAT was written and WHERE a recall spent its time (refactor2710-11, V2-826 §2b).

The viewer and the Master read memory through its events, so a pill grammar nobody can see is half a fix: each
written pill carries its `kind` (a `request` is told from a `result`), the result door says whether it accepted or
refused and why, and every recall leaves its milliseconds by phase (embed, lexical, vector, rerank). The events
are read as `voice.observer.emit` receives them; the store is a temp database and the embedding is local hashing.
"""
import asyncio

import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import queue as memqueue
from memory import writer as memwriter
from memory.retriever import recall
from nucleo import memory_agent
from nucleo.memory_agent import writer


@pytest.fixture
def events(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    seen: list[dict] = []
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None:
                        seen.append({"kind": kind, "label": label, "text": text, **(extra or {})}))
    yield seen
    memdb.reset_db()
    mememb.reset()


def _run(coro_fn):
    async def scenario():
        await memapi.start()
        out = await coro_fn()
        await memqueue.get_queue().join()
        await memapi.stop()
        return out
    return asyncio.run(scenario())


def test_each_written_pill_says_its_kind(events):
    async def go():
        await memory_agent.remember({"text": "Asked the assistant to book a table on Saturday.", "kind": "request",
                                     "level": "long", "importance": 0.6})
        await memory_agent.remember({"text": "Vive en Soria.", "kind": "fact", "level": "long", "importance": 0.6})
    _run(go)
    kinds = [e["kind"] for e in events if e.get("layer") == "write" and e["label"].startswith("píldora escrita")]
    assert kinds == ["request", "fact"], events


def test_the_result_door_reports_its_verdict(events):
    async def go():
        return [await writer.result("Found three carpenters.", task_id="t1", verdict="unmet"),
                await writer.result("Found three carpenters.", task_id="t2", verdict="met")]
    assert _run(go) == [False, True]
    door = [e for e in events if e.get("task_id") in ("t1", "t2")]
    assert [(e["task_id"], e["accepted"]) for e in door] == [("t1", False), ("t2", True)]
    assert "unmet" in door[0]["reason"] and door[1]["reason"] == ""


def test_a_recall_leaves_its_milliseconds_by_phase(events):
    memwriter.insert_memory("Le gustan los carpinteros de Soria.", kind="fact", level="long")
    hits = recall.search("carpinteros Soria", rerank=False, expand=False)
    assert hits
    timed = [e for e in events if e.get("layer") == "recall" and e["label"] == "recall medido"]
    assert len(timed) == 1, events
    ev = timed[0]
    for phase in ("embed_ms", "lexical_ms", "vector_ms", "rerank_ms", "total_ms"):
        assert isinstance(ev[phase], float) and ev[phase] >= 0, (phase, ev)
    assert ev["hits"] == len(hits) and ev["lexical_only"] is False
