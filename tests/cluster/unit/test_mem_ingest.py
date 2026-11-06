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


def test_disabled_is_noop(fresh_db, monkeypatch):
    monkeypatch.setenv("MESHKORE_MEMORY", "0")
    asyncio.run(_observe("obra", "Zalo", "algo", "respuesta"))
    assert memapi.recent_by_source("cluster", "Zalo") == []
