#
# test_realistic_session.py — V2-103 (2026-08-16): cierra el hueco estructural que dejó pasar los 3 bugs
# encontrados en una auditoría manual contra la BD REAL del operador (duplicados exactos entre turnos reales,
# backend de embeddings degradado-para-siempre, REM puramente aditivo). Ningún test anterior en el árbol llamaba
# a `memory_agent.ingest_utterance()` —el camino REAL de producción— dos veces con el mismo hecho; los tests de
# dedup existentes llamaban a `writer.insert_memory()` directamente, un camino más corto y artificial. Ningún
# test simulaba una degradación TRANSITORIA del backend de embeddings (falla al arrancar, se recupera después).
# Y el único test de sesión larga/volumen realista del árbol (`tests/memory/e2e/timeline/`) corría con la
# síntesis de REM explícitamente desactivada. Este fichero cubre las tres clases de una vez, por el camino real.
#
# Ejecutar: .venv/bin/pytest tests/memory/integration/test_realistic_session.py
#
import asyncio
import time

import pytest

from memory import api as memapi
from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import rem as memrem
from memory.queue import get_queue
from nucleo import memory_agent


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.delenv("FAST_API_KEY", raising=False)
    monkeypatch.setenv("MEM_PROCESSOR", "1")   # estos tests SIEMPRE ejercitan el camino LLM (mockeado)
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _atom(text, **overrides):
    a = {"text": text, "dest": "long", "kind": "fact", "importance": 0.7,
         "ttl_days": None, "slot": None, "state_patch": {}}
    a.update(overrides)
    return a


async def _ingest_many(texts_and_atoms):
    """Corre N turnos reales por `ingest_utterance()`, drenando la cola entre turnos (single writer real)."""
    await memapi.start()
    try:
        for raw, _atoms in texts_and_atoms:
            await memory_agent.ingest_utterance(raw)
            await get_queue().join()
    finally:
        await memapi.stop()


# ── 1. duplicado exacto entre DOS turnos reales (el incidente real: "Su suegro se llama Pedro." × 2) ──────────
def test_exact_repeat_across_two_real_turns_deduplicates(fresh_db, monkeypatch):
    """El CORAZÓN puede re-derivar el MISMO texto canónico en dos turnos adyacentes (el operador aclara/repite
    algo con otras palabras, el LLM destila al mismo hecho). Antes de V2-103 esto producía DOS filas `valid=1`."""
    async def fake_process(text, *, state=None):
        return [_atom("Su suegro se llama Pedro.")]

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", fake_process)

    asyncio.run(_ingest_many([
        ("Ah, y mi suegro se llama Pedro", None),
        ("Se me olvidó decir que mi suegro es Pedro", None),
    ]))
    db = memdb.get_db()
    rows = db.query("SELECT id, valid FROM memories WHERE text='Su suegro se llama Pedro.'")
    assert len(rows) == 1, "el CORAZÓN repitió el mismo hecho en dos turnos → debe quedar UNA sola fila"
    assert rows[0]["valid"] == 1


# ── 2. backend de embeddings con hipo TRANSITORIO al arrancar — el bug de fondo, de punta a punta ─────────────
def test_transient_ollama_hiccup_then_recovery_still_deduplicates(fresh_db, monkeypatch):
    # Este test prueba AUTODETECCIÓN real (hipo→degrada→recupera) — el `ZAELAR_EMBED_BACKEND=hash` del fixture
    # `_hash_backend` de arriba (autouse, para el resto del fichero) forzaría el backend y anularía justo el
    # mecanismo que se quiere probar. Hasta 2026-08-17 esto "funcionaba por accidente": un bug en
    # `_resolve_backend()` (memory/embeddings.py) ignoraba el env var siempre que la config mockeada dijera
    # "auto" — el fix de ese bug (V2-031) hace que el env var SÍ mande cuando existe, así que aquí hay que
    # despejarlo explícitamente para seguir probando lo que este test dice probar.
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    calls = {"ollama": 0}

    def flaky_ollama(texts, *, timeout=None):   # `timeout` lo pasa la sonda (V2-349)
        calls["ollama"] += 1
        return None if calls["ollama"] == 1 else [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(mememb, "_ollama_embed", flaky_ollama)
    monkeypatch.setattr(mememb, "_fastembed_embed", lambda texts: None)
    mememb.reset()
    assert mememb.active_backend() == "hash"   # arranque con hipo → degradado, como la noche del incidente

    async def fake_process(text, *, state=None):
        return [_atom("Han cancelado el viaje a Ibiza.")]

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", fake_process)

    asyncio.run(_ingest_many([
        ("cancelamos lo de Ibiza", None),
        ("por cierto, lo de Ibiza al final no se hace", None),
    ]))

    db = memdb.get_db()
    rows = db.query("SELECT id, valid FROM memories WHERE text='Han cancelado el viaje a Ibiza.'")
    assert len(rows) == 1, "el dedup EXACTO no depende del backend de embeddings — debe funcionar degradado"
    assert rows[0]["valid"] == 1

    # el backend se recupera SOLO tras el TTL, sin reiniciar el proceso (la causa raíz del bug real)
    t0 = time.time()
    monkeypatch.setattr(time, "time", lambda: t0 + mememb._BACKEND_RECHECK_S + 1)
    assert mememb.active_backend() == "ollama"


# ── 3. varios turnos reales → REM mejora la memoria de verdad, no solo "escribe una fila" ──────────────────────
def test_several_turns_then_rem_structurally_improves_memory(fresh_db, monkeypatch):
    turns = [
        ("por la tarde estuve escuchando a Mocedades", "escuchó a Mocedades por la tarde"),
        ("también puse a Serrat mientras trabajaba", "escuchó a Serrat mientras trabajaba"),
        ("me apetecía música de los ochenta", "pidió música de los ochenta"),
        ("sonó Tómame o Déjame en YouTube", "sonó Tómame o Déjame en YouTube"),
    ]
    call = {"i": -1}

    async def fake_process(text, *, state=None):
        call["i"] += 1
        _, canonical = turns[call["i"]]
        return [_atom(canonical, level="mid", kind="fact", concepts=["musica"])]

    from nucleo import mem_processor
    monkeypatch.setattr(mem_processor, "process", fake_process)
    asyncio.run(_ingest_many([(raw, None) for raw, _ in turns]))

    db = memdb.get_db()
    before = {r["id"]: r["weight"] for r in db.query(
        "SELECT id, weight FROM memories WHERE valid=1 AND kind='fact' AND slot IS NULL")}
    assert len(before) == 4, "las 4 píldoras de música deben existir, sin fusionarse (son distintas)"

    memcons.consolidate()   # sueño ligero real, como cada hora en producción

    def hook(groups):
        assert any(g["concept"] == "musica" for g in groups)
        return [{"concept": "musica", "insight": "Le gusta la música española clásica y la escucha trabajando."}]

    written = memrem.synthesize(hook, min_group=4)
    assert written == 1

    # (a) el insight existe y está vigente
    insight = db.query_one("SELECT id, text, valid FROM memories WHERE slot='insight:musica'")
    assert insight is not None and insight["valid"] == 1
    assert "música" in insight["text"]

    # (b) las píldoras crudas se demotaron — NUNCA invalidadas, pero pesan menos que antes
    ph = ",".join("?" * len(before))
    after = {r["id"]: (r["weight"], r["valid"], r["meta"]) for r in db.query(
        f"SELECT id, weight, valid, meta FROM memories WHERE id IN ({ph})", tuple(before))}
    for mid, w0 in before.items():
        w1, valid1, meta1 = after[mid]
        assert valid1 == 1, f"la píldora {mid} NUNCA debe invalidarse por REM"
        assert w1 < w0, f"la píldora {mid} debe pesar MENOS tras la síntesis (antes {w0}, ahora {w1})"
        assert f'"summarized_by": {insight["id"]}' in (meta1 or "")

    # (c) mejora MEDIBLE: una consulta sobre el tema trae el insight, no solo el ruido disperso
    result = memapi.query("qué música le gusta", limit=5, reinforce_used=False)
    ids = result["ids"]
    assert insight["id"] in ids, "el insight sintetizado debe aparecer en el recall del tema que resume"


def test_rem_runs_repeatedly_without_duplicating_insights(fresh_db, monkeypatch):
    """Varias tandas de turnos → varios ciclos de sueño ligero + REM (la cadencia real de producción, repetida
    varias veces): el insight se REESCRIBE por slot, nunca se acumulan insights duplicados del mismo concepto,
    y la 2ª tanda de píldoras también acaba demotada tras la 2ª síntesis."""
    batch1 = ["escuchó a Mocedades por la tarde", "escuchó a Serrat mientras trabajaba",
              "pidió música de los ochenta", "sonó Tómame o Déjame en YouTube"]
    batch2 = ["puso a Rocío Jurado el domingo", "escuchó copla toda la mañana",
              "pidió sevillanas para la fiesta", "sonó flamenco en la radio"]

    def make_process(batch):
        idx = {"i": -1}

        async def fake_process(text, *, state=None):
            idx["i"] += 1
            return [_atom(batch[idx["i"]], level="mid", kind="fact", concepts=["musica"])]
        return fake_process

    from nucleo import mem_processor

    monkeypatch.setattr(mem_processor, "process", make_process(batch1))
    asyncio.run(_ingest_many([(t, None) for t in batch1]))
    memcons.consolidate()
    written1 = memrem.synthesize(lambda groups: [{"concept": "musica", "insight": "Le gusta la música clásica española."}],
                                  min_group=4)
    assert written1 == 1
    db = memdb.get_db()
    insight_1 = db.query_one("SELECT id, text FROM memories WHERE slot='insight:musica' AND valid=1")

    monkeypatch.setattr(mem_processor, "process", make_process(batch2))
    asyncio.run(_ingest_many([(t, None) for t in batch2]))
    memcons.consolidate()
    written2 = memrem.synthesize(
        lambda groups: [{"concept": "musica", "insight": "Su gusto musical abarca copla y flamenco andaluz."}],
        min_group=4)
    assert written2 == 1

    all_insights = db.query("SELECT id, text, valid FROM memories WHERE slot='insight:musica'")
    valid_insights = [r for r in all_insights if r["valid"] == 1]
    assert len(valid_insights) == 1, "el insight se REESCRIBE (supersede por slot), nunca se acumula"
    assert valid_insights[0]["id"] != insight_1["id"]
    assert "flamenco" in valid_insights[0]["text"]

    # todas las píldoras de la 2ª tanda (batch2) también quedaron demotadas por la 2ª síntesis
    rows2 = db.query("SELECT meta, valid FROM memories WHERE valid=1 AND text IN (%s)" %
                      ",".join("?" * len(batch2)), tuple(batch2))
    assert len(rows2) == len(batch2)
    for r in rows2:
        assert "summarized_by" in (r["meta"] or "")
