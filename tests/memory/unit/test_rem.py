"""Tests del sueño PROFUNDO «fase REM» (memory/rem.py, V2-056). Deterministas: backend hash, hook inyectado."""
import time

import pytest

from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import rem as memrem
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
    # apaga el dedup semántico DEL WRITER (T125) — aquí probamos el de REM aislado (si no, el writer fusiona
    # los duplicados de la fixture en el propio insert y REM nunca los ve)
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
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


def test_due_seeds_then_fires(fresh_db, monkeypatch):
    now = int(time.time())
    assert memrem.due(now) is False                       # 1ª vez: siembra el marcador, no corre
    assert memrem.due(now + 3600) is False                # dentro de la cadencia
    assert memrem.due(now + int(memrem.every_s()) + 10) is True
    monkeypatch.setenv("ZAELAR_REM", "0")
    assert memrem.due(now + 10 * 86400) is False          # kill-switch


def test_semantic_dedup_merges_echoes(fresh_db):
    # mismo multiconjunto de tokens, orden distinto → el embedding hash (léxico) los ve idénticos
    a = memwriter.insert_memory("tiene cita para la ITV el jueves 23", level="mid", kind="fact", weight=0.8)
    b = memwriter.insert_memory("el jueves 23 tiene cita para la ITV", level="mid", kind="fact", weight=0.5)
    merged = memrem.semantic_dedup(threshold=0.95)
    assert merged == 1
    db = memdb.get_db()
    rb = db.query_one("SELECT valid, superseded_by FROM memories WHERE id=?", (b,))
    assert rb["valid"] == 0 and rb["superseded_by"] == a   # gana el de mayor peso; histórico intacto
    ra = db.query_one("SELECT valid FROM memories WHERE id=?", (a,))
    assert ra["valid"] == 1


def test_semantic_dedup_respects_slots_and_pinned(fresh_db):
    memwriter.insert_memory("dato con slot", level="long", kind="fact", slot="goal.current")
    memwriter.insert_memory("con slot dato", level="long", kind="fact", slot="goal.current")
    # con slot NO entra al dedup semántico (ya supersede exacto por slot en el writer)
    assert memrem.semantic_dedup(threshold=0.9) == 0


def test_synthesize_writes_insight_with_supersede(fresh_db):
    for i, t in enumerate(["escuchó a Mocedades por la tarde", "escuchó a Serrat mientras trabajaba",
                           "pidió música de los ochenta", "sonó Tómame o Déjame en YouTube"]):
        memwriter.insert_memory(t, level="mid", kind="fact", concepts=["musica"])
    hook_calls = []

    def hook(groups):
        hook_calls.append(groups)
        return [{"concept": "musica", "insight": "Le gusta la música española clásica y la escucha mientras trabaja."}]

    assert memrem.synthesize(hook, min_group=4) == 1
    db = memdb.get_db()
    rows = db.query("SELECT id, valid, text FROM memories WHERE slot='insight:musica'")
    assert len(rows) == 1 and rows[0]["valid"] == 1
    assert "música" in rows[0]["text"]
    assert hook_calls and hook_calls[0][0]["concept"] == "musica" and len(hook_calls[0][0]["pills"]) >= 4
    # segundo sueño → el insight se REESCRIBE (supersede por slot), no se acumula
    def hook2(groups):
        return [{"concept": "musica", "insight": "Su música de cabecera es la canción española de los 70-80."}]
    assert memrem.synthesize(hook2, min_group=4) == 1
    valid = db.query("SELECT text FROM memories WHERE slot='insight:musica' AND valid=1")
    assert len(valid) == 1 and "70-80" in valid[0]["text"]


def test_synthesize_failopen_without_hook(fresh_db):
    assert memrem.synthesize(None) == 0


def test_hygiene_alerts_on_heuristic_flood(fresh_db):
    for i in range(12):
        memwriter.insert_memory(f"crudo {i}", level="mid", kind="fact",
                                meta={"source": "voice", "path": "heuristic"})
    h = memrem.hygiene()
    assert h["written_24h"] >= 12 and h["heuristic_pct"] > 90 and h["alert"] is True


def test_run_full_cycle_reports(fresh_db):
    memwriter.insert_memory("un dato", level="mid", kind="fact")
    rep = memrem.run(synthesize_fn=None)
    assert set(rep) >= {"repaired", "sem_deduped", "insights", "hygiene", "ms"}
    # el marcador queda sembrado → el próximo due() respeta cadencia
    assert memrem.due() is False
