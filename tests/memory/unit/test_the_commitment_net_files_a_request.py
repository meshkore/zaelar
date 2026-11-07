"""V2-858 T547 — the commitment net files a REQUEST, never the literal order as an event.

Measured origin (live store, 2026-11-06): 32 rows written by the commitment net as `long/event` with the literal
turn («manda un mensaje a raquel…», «find me five days in her vacation…»), and 31 of them sat next to the
`request` the HEART had already filed for the same turn. Months later an order reads back as something that
happened, and every recall of «what did I ask you» pays two rows for one fact.

The class: a backstop backs up a MISS. When the model already filed the turn's request the net writes nothing;
when the model dropped it (or is down) the net writes a dated `request`. The stock is healed by light sleep
(`consolidator.heal_commitment_net`). Cases in ES and EN enter through `ingest_utterance` with the HEART mocked
at the real seam (`distill.process`).
"""
import asyncio
import json
import time

import pytest

from memory import api as memapi
from memory import consolidator as memcons
from memory import db as memdb
from memory import queue as memqueue
from memory import writer as memwriter
from nucleo import memory_agent
from nucleo.memory_agent import ingest_steps, request_frame  # named so `--impacted` reaches this file

ES = "manda un mensaje a raquel, pregúntale cómo va y a qué hora llega"
EN = "find me five days in her vacation where i'm free and tell me the dates"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEM_PROCESSOR", "0")
    monkeypatch.setenv("MEMORY_RERANK", "off")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _heart(monkeypatch, atoms):
    from nucleo.memory_agent.processor import distill, distill_config

    async def _process(_t, state=None):
        return [dict(a) for a in atoms]

    monkeypatch.setattr(distill, "process", _process)
    monkeypatch.setattr(distill_config, "enabled", lambda: True)


def _ingest(u):
    async def scenario():
        await memapi.start()
        out = await memory_agent.ingest_utterance(u, role="operator")
        await memqueue.get_queue().join()
        await memapi.stop()
        return out
    return asyncio.run(scenario())


def _rows():
    return memdb.get_db().query("SELECT id, kind, level, valid, text, meta FROM memories WHERE kind<>'concept' "
                                "AND kind<>'conv'")


def _net_rows():
    return [r for r in _rows() if json.loads(r["meta"] or "{}").get("path") == "commitment-net"]


def _request_atom(text):
    return {"text": text, "dest": "long", "kind": "request", "importance": 0.6, "ttl_days": None, "slot": None,
            "value": None, "change": None, "concepts": [], "state_patch": {}, "supersedes": []}


@pytest.mark.parametrize("turn,filed", [
    (ES, "Asked the assistant to send Raquel a message asking how she is and when she arrives (4 Nov 2026)."),
    (EN, "Asked the assistant to find five free days in her vacation and tell him the dates (4 Nov 2026)."),
])
def test_a_request_the_heart_filed_gets_no_raw_twin(fresh_db, monkeypatch, turn, filed):
    _heart(monkeypatch, [_request_atom(filed)])
    _ingest(turn)
    assert _net_rows() == [], "the net duplicated a request the HEART had already filed"
    assert [r["kind"] for r in _rows() if r["valid"]] == ["request"]


@pytest.mark.parametrize("turn", [ES, EN])
def test_a_request_the_heart_dropped_is_kept_as_a_dated_request(fresh_db, monkeypatch, turn):
    _heart(monkeypatch, [])                       # the model ran and discarded the order
    _ingest(turn)
    net = _net_rows()
    assert len(net) == 1
    assert net[0]["kind"] == "request", "an order kept by the net must never read back as an event"
    assert net[0]["text"].startswith("[20") and turn.split()[0] in net[0]["text"]
    assert json.loads(net[0]["meta"])["said_at"]


def test_light_sleep_heals_the_stock_the_old_net_left(fresh_db):
    now = int(time.time())
    filed = memwriter.insert_memory("Asked the assistant to message Raquel (4 Nov 2026).", level="long",
                                    kind="request")
    twin = memwriter.insert_memory(ES, level="long", kind="event",
                                   meta={"source": "voice", "path": "commitment-net"})
    lone = memwriter.insert_memory(EN, level="long", kind="event",
                                   meta={"source": "voice", "path": "commitment-net"})
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (now - 86400 * 9, lone))
    rep = memcons.consolidate(limit=1000)
    assert rep["healed_commitment_net"] == {"superseded": 1, "retyped": 1}
    by = {r["id"]: r for r in memdb.get_db().query("SELECT id, kind, valid, superseded_by FROM memories")}
    assert by[twin]["valid"] == 0 and by[twin]["superseded_by"] == filed      # history kept, pointed at its twin
    assert by[lone]["valid"] == 1 and by[lone]["kind"] == "request"
    assert memcons.heal_commitment_net() == {"superseded": 0, "retyped": 0}      # idempotent


def test_the_net_reads_the_memory_clock_not_the_wall(fresh_db):
    """The request's date is the day it was SAID: a simulated or replayed day must stamp its own date."""
    from memory.clock import travel
    with travel(int(time.mktime((2027, 3, 14, 12, 0, 0, 0, 0, -1)))):
        assert request_frame.today_iso() == "2027-03-14"
        assert request_frame.dated("  llama a Ana  ") == "[2027-03-14] llama a Ana"
    assert ingest_steps._request_frame is request_frame          # the net files through this frame
