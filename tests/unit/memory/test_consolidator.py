"""Tests de memory/consolidator.py (V2-002 · T49) — decay, eviction (pinned intocable), dedup, promoción."""
import time

import pytest

from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


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


def test_decay_lowers_weight_of_stale(fresh_db):
    now = int(time.time())
    mid = memwriter.insert_memory("dato viejo", weight=0.8)
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now - 10 * 86400, mid))
    # Decay por VENTANA (2026-07-20): Δt = now − max(last_access, último ciclo) → sembramos el marcador 10 días
    # atrás para que la ventana cubra toda la inactividad (sin marcador, el primer decay solo inicializa).
    memcons._kv_set("decay_last_run", str(now - 10 * 86400))
    memcons.decay(now=now, lam=0.1)  # λ alto para ver el efecto: factor ≈ e^-1
    w = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (mid,))["weight"]
    assert w < 0.8 and w == pytest.approx(0.8 * 2.718281828 ** -1, rel=0.02)


def test_access_resets_decay(fresh_db):
    now = int(time.time())
    stale = memwriter.insert_memory("viejo", weight=0.8)
    fresh = memwriter.insert_memory("reciente", weight=0.8)
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now - 20 * 86400, stale))
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now, fresh))
    memcons._kv_set("decay_last_run", str(now - 20 * 86400))
    memcons.decay(now=now, lam=0.1)
    ws = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (stale,))["weight"]
    wf = memdb.get_db().query_one("SELECT weight FROM memories WHERE id=?", (fresh,))["weight"]
    assert wf > ws  # el reciente (acceso reciente) decae mucho menos


def test_evict_only_over_limit(fresh_db):
    for i in range(3):
        memwriter.insert_memory(f"m{i}", weight=0.5)
    assert memcons.evict(limit=10) == 0  # bajo el límite → no borra nada
    assert memcons.count() == 3


def test_evict_removes_lowest_weight(fresh_db):
    a = memwriter.insert_memory("bajo", weight=0.1)
    b = memwriter.insert_memory("alto", weight=0.9)
    removed = memcons.evict(limit=1)
    assert removed == 1
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert a not in ids and b in ids  # se fue el de menor peso


def test_pinned_never_evicted(fresh_db):
    pin = memwriter.insert_memory("clave del ledger", weight=0.01, pinned=True)  # peso ínfimo pero pinned
    for i in range(3):
        memwriter.insert_memory(f"relleno{i}", weight=0.9)
    memcons.evict(limit=1)  # fuerza mucho olvido
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert pin in ids  # el pinned SIEMPRE sobrevive
    # y solo queda el pinned si todo lo demás era borrable
    assert memcons.count() == 1


def test_dedup_merges_identical_text(fresh_db):
    a = memwriter.insert_memory("El Operador  se llama Ricart", weight=0.5)
    b = memwriter.insert_memory("el operador se llama ricart", weight=0.8)  # mismo normalizado
    c = memwriter.insert_memory("otra cosa", weight=0.5)
    removed = memcons.dedup()
    assert removed == 1
    ids = {r["id"] for r in memdb.get_db().query("SELECT id FROM memories")}
    assert b in ids and c in ids and a not in ids  # conserva el de mayor peso (b)


def test_promote_by_age(fresh_db):
    now = int(time.time())
    old = memwriter.insert_memory("viejo corto", level="short")
    memdb.get_db().execute("UPDATE memories SET created=? WHERE id=?", (now - 5 * 86400, old))
    young = memwriter.insert_memory("corto reciente", level="short")
    rep = memcons.promote(now=now)
    assert rep["short_to_mid"] == 1
    assert memdb.get_db().query_one("SELECT level FROM memories WHERE id=?", (old,))["level"] == "mid"
    assert memdb.get_db().query_one("SELECT level FROM memories WHERE id=?", (young,))["level"] == "short"


def test_consolidate_reports(fresh_db):
    memwriter.insert_memory("uno", weight=0.5)
    memwriter.insert_memory("dos", weight=0.5)
    rep = memcons.consolidate(limit=1000)
    assert set(rep) == {"healed_slots", "promoted", "deduped", "decayed", "pruned", "evicted", "count"}
    assert rep["count"] == 2
