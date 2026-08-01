#
# Tests de la OBSERVACIÓN PASIVA cluster→memoria (connectors/meshkore/mem_ingest.py, V2-021 T170).
# Run: .venv/bin/pytest tests/cluster/unit/test_mem_ingest.py -q
#
# Verifica el invariante central: un intercambio con un peer produce una SÍNTESIS COMPRIMIDA recuperable por
# `recent_by_source("cluster", <peer>)`, CUARENTENADA (nunca en `recent_short`/`salient_long` ni en el recall),
# y EVOLUTIVA (un solo registro por peer, se sobrescribe por slot).
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
    """Corre _run (el trabajo real) con la cola arrancada y drenada, para que la escritura quede en la BD."""
    await memapi.start()
    await mem_ingest._run(cluster, peer, inbound, outbound)
    await get_queue().join()
    await memapi.stop()


def test_exchange_becomes_quarantined_synthesis(fresh_db, monkeypatch):
    # Sintetizador determinista (sin depender de un LLM local en CI).
    async def fake_summarize(peer, prev, inbound, outbound):
        return "Hablan de un sistema de riego con ESP32; acuerdan compartir el esquema."
    monkeypatch.setattr(mem_ingest, "_summarize", fake_summarize)

    asyncio.run(_observe("obra", "Zalo",
                         "tengo un sistema de riego con esp32, ¿me ayudas con el esquema?",
                         "claro, te paso un esquema base con relés"))

    # RECUPERABLE por índice de fuente (consulta EXPLÍCITA).
    cluster = " ".join(r["text"] for r in memapi.recent_by_source("cluster", "Zalo"))
    assert "riego" in cluster and "esp32" in cluster.lower()
    # marcada untrusted
    rows = memapi.recent_by_source("cluster", "Zalo")
    assert rows and rows[0]["trust"] == "untrusted" and rows[0]["source"] == "cluster"

    # CUARENTENA: NO en el bloque pasivo del FlashBrain.
    passive_short = " ".join(r["text"] for r in memapi.recent_short(limit=50))
    passive_long = " ".join(r["text"] for r in memapi.salient_long(limit=8))
    assert "riego" not in passive_short and "riego" not in passive_long

    # CUARENTENA: tampoco por recall semántico (el retriever excluye untrusted).
    recall = " ".join(m["text"] for m in memapi.query("sistema de riego esp32")["memories"])
    assert "riego" not in recall


def test_synthesis_is_evolutive_one_row_per_peer(fresh_db, monkeypatch):
    calls = {"n": 0}

    async def fake_summarize(peer, prev, inbound, outbound):
        calls["n"] += 1
        # la 2ª vez integra lo previo → síntesis actualizada (supersede)
        return f"v{calls['n']}: temas acumulados con {peer}"
    monkeypatch.setattr(mem_ingest, "_summarize", fake_summarize)

    asyncio.run(_observe("obra", "Zalo", "hola, hablemos de sensores", "vale"))
    asyncio.run(_observe("obra", "Zalo", "y también de bombas de agua", "de acuerdo"))

    # UNA sola fila VÁLIDA bajo el slot (supersede exacto), con la síntesis MÁS RECIENTE.
    rows = memapi.recent_by_source("cluster", "Zalo")
    assert len(rows) == 1
    assert "v2" in rows[0]["text"]
    # y el sintetizador vio la síntesis previa en la 2ª llamada (evolutiva)
    assert calls["n"] == 2


def test_fail_open_deterministic_merge_stays_bounded(fresh_db, monkeypatch):
    # modelo NO disponible → _summarize devuelve None → fusión determinista ACOTADA (nunca crece sin límite).
    async def no_model(peer, prev, inbound, outbound):
        return None
    monkeypatch.setattr(mem_ingest, "_summarize", no_model)

    for i in range(40):
        asyncio.run(_observe("obra", "Bee", f"mensaje larguísimo número {i} " * 30, "ok"))

    rows = memapi.recent_by_source("cluster", "Bee")
    assert len(rows) == 1                                   # sigue siendo UNA fila (supersede)
    synth = rows[0]["text"].split(": ", 1)[-1]
    assert len(synth) <= mem_ingest._MAX_SYNTH + 5          # acotada pese a 40 intercambios enormes


def test_disabled_is_noop(fresh_db, monkeypatch):
    monkeypatch.setenv("MESHKORE_MEMORY", "0")
    asyncio.run(_observe("obra", "Zalo", "algo", "respuesta"))
    assert memapi.recent_by_source("cluster", "Zalo") == []
