#
# test_realistic_session.py — V2-103 (2026-08-16): closes the structural gap that allowed the 3 bugs
# found in a manual audit against the operator's REAL DB (exact duplicates across real turns,
# embeddings backend degraded-forever, purely additive REM). No earlier test in the tree called
# `memory_agent.ingest_utterance()` twice with the same fact—the REAL production path; the existing dedup tests
# called `writer.insert_memory()` directly, a shorter and artificial path. No test simulated a TRANSIENT
# degradation of the embeddings backend (fails on startup, recovers later). And the only realistic long-session/
# volume test in the tree (`tests/memory/e2e/timeline/`) ran with REM synthesis explicitly disabled. This file
# covers all three classes at once, through the real path.
#
# Run: .venv/bin/pytest tests/memory/integration/test_realistic_session.py
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
    monkeypatch.setenv("MEM_PROCESSOR", "1")   # these tests ALWAYS exercise the (mocked) LLM path
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
    """Runs N real turns through `ingest_utterance()`, draining the queue between turns (real single writer)."""
    await memapi.start()
    try:
        for raw, _atoms in texts_and_atoms:
            await memory_agent.ingest_utterance(raw)
            await get_queue().join()
    finally:
        await memapi.stop()


# ── 1. exact duplicate across TWO real turns (the real incident: "Su suegro se llama Pedro." × 2) ──────────
def test_exact_repeat_across_two_real_turns_deduplicates(fresh_db, monkeypatch):
    """The CORE can re-derive the SAME canonical text in two adjacent turns (the operator clarifies/repeats
    something in other words, and the LLM distills it to the same fact). Before V2-103 this produced TWO `valid=1` rows."""
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
    assert len(rows) == 1, "the CORE repeated the same fact in two turns → only ONE row should remain"
    assert rows[0]["valid"] == 1


# ── 2. embeddings backend with a TRANSIENT startup hiccup — the underlying bug, end to end ─────────────
def test_transient_ollama_hiccup_then_recovery_still_deduplicates(fresh_db, monkeypatch):
    # This test verifies real AUTO-DETECTION (hiccup→degrade→recover)—the fixture's
    # `ZAELAR_EMBED_BACKEND=hash` from `_hash_backend` above (autouse, for the rest of the file) would force the
    # backend and disable precisely the mechanism under test. Until 2026-08-17 this "worked by accident": a bug in
    # `_resolve_backend()` (memory/embeddings.py) ignored the env var whenever the mocked config said "auto"—the
    # fix for that bug (V2-031) makes the env var take precedence when present, so it must be explicitly cleared
    # here to keep testing what this test claims to test.
    monkeypatch.delenv("ZAELAR_EMBED_BACKEND", raising=False)
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "auto", "embed_model": ""})
    calls = {"ollama": 0}

    def flaky_ollama(texts, *, timeout=None):   # `timeout` is passed by the probe (V2-349)
        calls["ollama"] += 1
        return None if calls["ollama"] == 1 else [[0.1] * 768 for _ in texts]

    monkeypatch.setattr(mememb, "_ollama_embed", flaky_ollama)
    monkeypatch.setattr(mememb, "_fastembed_embed", lambda texts: None)
    mememb.reset()
    assert mememb.active_backend() == "hash"   # startup hiccup → degraded, as on the night of the incident

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
    assert len(rows) == 1, "EXACT dedup does not depend on the embeddings backend—it must work while degraded"
    assert rows[0]["valid"] == 1

    # the backend recovers ONLY after the TTL, without restarting the process (the root cause of the real bug)
    t0 = time.time()
    monkeypatch.setattr(time, "time", lambda: t0 + mememb._BACKEND_RECHECK_S + 1)
    assert mememb.active_backend() == "ollama"


# ── 3. several real turns → REM genuinely improves memory, rather than merely "writing a row" ──────────────────────
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
    assert len(before) == 4, "the 4 music pills must exist without being merged (they are distinct)"

    memcons.consolidate()   # real light sleep, as every hour in production

    def hook(groups):
        assert any(g["concept"] == "musica" for g in groups)
        return [{"concept": "musica", "insight": "Le gusta la música española clásica y la escucha trabajando."}]

    written = memrem.synthesize(hook, min_group=4)
    assert written == 1

    # (a) the insight exists and is current
    insight = db.query_one("SELECT id, text, valid FROM memories WHERE slot='insight:musica'")
    assert insight is not None and insight["valid"] == 1
    assert "música" in insight["text"]

    # (b) the raw pills were demoted—NEVER invalidated, but weigh less than before
    ph = ",".join("?" * len(before))
    after = {r["id"]: (r["weight"], r["valid"], r["meta"]) for r in db.query(
        f"SELECT id, weight, valid, meta FROM memories WHERE id IN ({ph})", tuple(before))}
    for mid, w0 in before.items():
        w1, valid1, meta1 = after[mid]
        assert valid1 == 1, f"pill {mid} must NEVER be invalidated by REM"
        assert w1 < w0, f"pill {mid} must weigh LESS after synthesis (before {w0}, now {w1})"
        assert f'"summarized_by": {insight["id"]}' in (meta1 or "")

    # (c) MEASURABLE improvement: a query about the topic returns the insight, not just scattered noise
    result = memapi.query("qué música le gusta", limit=5, reinforce_used=False)
    ids = result["ids"]
    assert insight["id"] in ids, "el insight sintetizado debe aparecer en el recall del tema que resume"


def test_rem_runs_repeatedly_without_duplicating_insights(fresh_db, monkeypatch):
    """Several batches of turns → several light-sleep + REM cycles (the real production cadence, repeated
    several times): the insight is REWRITTEN by slot, duplicate insights for the same concept never accumulate,
    and the 2nd batch of pills also ends up demoted after the 2nd synthesis."""
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
    assert len(valid_insights) == 1, "the insight is REWRITTEN (superseded by slot), never accumulated"
    assert valid_insights[0]["id"] != insight_1["id"]
    assert "flamenco" in valid_insights[0]["text"]

    # all pills from the 2nd batch (batch2) were also demoted by the 2nd synthesis
    rows2 = db.query("SELECT meta, valid FROM memories WHERE valid=1 AND text IN (%s)" %
                      ",".join("?" * len(batch2)), tuple(batch2))
    assert len(rows2) == len(batch2)
    for r in rows2:
        assert "summarized_by" in (r["meta"] or "")
