#
# Tests of PASSIVE OBSERVATION cluster→memory (connectors/meshkore/mem_ingest.py, V2-021 T170).
# Run: .venv/bin/pytest tests/cluster/unit/test_mem_ingest.py -q
#
# Verifies the central invariant: an exchange with a peer produces a COMPRESSED SYNTHESIS retrievable by
# `recent_by_source("cluster", <peer>)`, QUARANTINED (never in `recent_short`/`salient_long` or recall),
# and EVOLVING (a single record per peer, overwritten by slot).
#
import asyncio

import pytest

from connectors.meshkore import mem_ingest
from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory.queue import get_queue


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


async def _observe(cluster, peer, inbound, outbound):
    """Runs _run (the actual work) with the queue started and drained so that the write remains in the database."""
    await memapi.start()
    await mem_ingest._run(cluster, peer, inbound, outbound)
    await get_queue().join()
    await memapi.stop()


def test_exchange_becomes_quarantined_synthesis(fresh_db, monkeypatch):
    # Deterministic synthesizer (without depending on a local LLM in CI).
    async def fake_summarize(peer, prev, inbound, outbound):
        return "Hablan de un sistema de riego con ESP32; acuerdan compartir el esquema."
    monkeypatch.setattr(mem_ingest, "_summarize", fake_summarize)

    asyncio.run(_observe("obra", "Zalo",
                         "tengo un sistema de riego con esp32, ¿me ayudas con el esquema?",
                         "claro, te paso un esquema base con relés"))

    # RETRIEVABLE by source index (EXPLICIT query).
    cluster = " ".join(r["text"] for r in memapi.recent_by_source("cluster", "Zalo"))
    assert "riego" in cluster and "esp32" in cluster.lower()
    # marked untrusted
    rows = memapi.recent_by_source("cluster", "Zalo")
    assert rows and rows[0]["trust"] == "untrusted" and rows[0]["source"] == "cluster"

    # QUARANTINE: NOT in FlashBrain's passive block.
    passive_short = " ".join(r["text"] for r in memapi.recent_short(limit=50))
    passive_long = " ".join(r["text"] for r in memapi.salient_long(limit=8))
    assert "riego" not in passive_short and "riego" not in passive_long

    # QUARANTINE: not through semantic recall either (the retriever excludes untrusted).
    recall = " ".join(m["text"] for m in memapi.query("sistema de riego esp32")["memories"])
    assert "riego" not in recall


def test_synthesis_is_evolutive_one_row_per_peer(fresh_db, monkeypatch):
    calls = {"n": 0}

    async def fake_summarize(peer, prev, inbound, outbound):
        calls["n"] += 1
        # The 2nd time it incorporates the previous result → updated synthesis (supersede)
        return f"v{calls['n']}: temas acumulados con {peer}"
    monkeypatch.setattr(mem_ingest, "_summarize", fake_summarize)

    asyncio.run(_observe("obra", "Zalo", "hola, hablemos de sensores", "vale"))
    asyncio.run(_observe("obra", "Zalo", "y también de bombas de agua", "de acuerdo"))

    # A single VALID row under the slot (exact supersede), with the MOST RECENT synthesis.
    rows = memapi.recent_by_source("cluster", "Zalo")
    assert len(rows) == 1
    assert "v2" in rows[0]["text"]
    # And the synthesizer saw the previous synthesis on the 2nd call (evolving)
    assert calls["n"] == 2


def test_fail_open_deterministic_merge_stays_bounded(fresh_db, monkeypatch):
    # Model NOT available → _summarize returns None → BOUNDED deterministic merge (never grows without limit).
    async def no_model(peer, prev, inbound, outbound):
        return None
    monkeypatch.setattr(mem_ingest, "_summarize", no_model)

    for i in range(40):
        asyncio.run(_observe("obra", "Bee", f"mensaje larguísimo número {i} " * 30, "ok"))

    rows = memapi.recent_by_source("cluster", "Bee")
    assert len(rows) == 1                                   # remains a SINGLE row (supersede)
    synth = rows[0]["text"].split(": ", 1)[-1]
    assert len(synth) <= mem_ingest._MAX_SYNTH + 5          # bounded despite 40 huge exchanges


def test_disabled_is_noop(fresh_db, monkeypatch):
    monkeypatch.setenv("MESHKORE_MEMORY", "0")
    asyncio.run(_observe("obra", "Zalo", "algo", "respuesta"))
    assert memapi.recent_by_source("cluster", "Zalo") == []
