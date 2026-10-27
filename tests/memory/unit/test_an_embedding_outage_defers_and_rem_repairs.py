"""Embeddings have NO cross-model failover — the outage is DEFERRED, end to end (V2-824, CRIT-R3).

A different embedding model is a different vector space: a stand-in would answer in coordinates no stored
pill can be compared with, so mixing them corrupts recall and dedup (V2-482/484/485). The only honest stand-in
is the SAME model through another endpoint, and the table declares none. What has to hold instead, walked here
through the real modules rather than asserted on a flag:

  1. the titular is down → the pill is WRITTEN anyway, without a vector, marked `meta.embed_pending="degraded"`;
  2. recall still finds it through FTS5 (the lexical half of the fusion) and the health light says amber;
  3. the titular comes back → REM's `repair_embeddings` gives the pill its vector and pops the marker;
  4. at no point did the backend change: the signature stays the titular's.

Plus the rule itself on the table: `failover` is null, and if somebody ever fills it, it must name the SAME
model (same `model`, same `dims`) — anything else is a space swap dressed as a stand-in.
"""
from __future__ import annotations

import json

import pytest

from config import models as table
from memory import db as memdb
from memory import embeddings as emb
from memory import reembed as memreembed
from memory import rem as memrem
from memory import retriever as memret
from memory import writer as memwriter
from voice import health_state

_DIM = 768


def _fake_cloud(texts, *, timeout=None):
    """A deterministic 'cloud' answer: the hash vector, which is enough to be a vector of the right width."""
    return [emb._l2_normalize(emb._fit_dim(emb._hash_embed(t, _DIM), _DIM)) for t in texts]


@pytest.fixture(autouse=True)
def _cloud_titular(monkeypatch):
    """The backend is the table's titular, DECLARED (never inherited from the machine), and nothing here reaches
    the network: `_cloud_embed` is replaced per step."""
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai", "embed_model": "text-embedding-3-small"})
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)
    yield
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)
    health_state.clear("memory")


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _marker(mid: int):
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    return json.loads(row["meta"] or "{}").get("embed_pending")


def _has_vector(mid: int) -> bool:
    return memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,)) is not None


# ── the table's rule ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_embeddings_row_declares_no_failover():
    assert table.failover("embeddings") is None, (
        "a second embedding model is another vector space, not a stand-in — see the row's `warning`")


def test_a_failover_if_ever_declared_must_be_the_SAME_model():
    """The one legitimate stand-in: the same model through another door. Simulated on a copy of the row so the
    rule is pinned even while the real row is null."""
    svc = dict(table.service("embeddings"))
    titular = svc["titular"]
    same_door = {**titular, "provider": "azure", "base_url": "https://other.example/v1", "key_env": "OTHER_KEY"}
    other_model = {**same_door, "model": "mistral-embed"}
    assert _same_space(titular, same_door)
    assert not _same_space(titular, other_model)


def _same_space(a: dict, b: dict) -> bool:
    return a.get("model") == b.get("model") and a.get("dims") == b.get("dims")


# ── the outage, end to end ────────────────────────────────────────────────────────────────────────────────────

def test_an_outage_writes_the_pill_defers_the_vector_and_rem_repairs_it(fresh_db, monkeypatch):
    # seal the space with the titular while it answers, so there IS a space to defend
    monkeypatch.setattr(emb, "_cloud_embed", _fake_cloud)
    first = memwriter.insert_memory("Su dentista está en la calle Mayor.", level="long", kind="fact")
    assert _has_vector(first)
    memreembed.stamp()
    assert memreembed.stored_signature() == "cloud:text-embedding-3-small:768"

    # 1. the titular goes down: a 429, a dead key — `_cloud_embed` answers None
    monkeypatch.setattr(emb, "_cloud_embed", lambda texts, *, timeout=None: None)
    mid = memwriter.insert_memory("Le operan de la rodilla el martes.", level="long", kind="event")
    assert mid, "the pill is written even when it cannot be embedded"
    assert not _has_vector(mid), "no vector from an emergency hash may enter the titular's space"
    assert _marker(mid) == "degraded"
    assert emb.active_backend() == "cloud", "the space is never swapped in flight"
    assert memreembed.signature() == memreembed.stored_signature()

    # 2. recall still finds it, lexically, and says amber
    hits = memret.search("rodilla martes", k=10, limit=5)
    assert any(h["id"] == mid for h in hits), "FTS5 carries the read while the vector is missing"
    light = health_state.get("memory") or {}
    assert light.get("kind") == "degraded" and "embedder" in str(light.get("text", "")).lower(), light

    # 3. the titular comes back → the nightly repair embeds it and clears the marker
    monkeypatch.setattr(emb, "_cloud_embed", _fake_cloud)
    emb.embed("ping")                                      # a live call succeeds → `last_degraded` clears
    assert memrem.repair_embeddings(limit=50) >= 1
    assert _has_vector(mid)
    assert _marker(mid) is None

    # 4. and the semantic half is back: the query vector now matches the stored one
    hits = memret.search("Le operan de la rodilla el martes.", k=10, limit=5)
    assert hits and hits[0]["id"] == mid


def test_a_recall_during_the_outage_does_not_fuse_an_emergency_vector(fresh_db, monkeypatch):
    """The read half of the same rule: with the titular down, the query is NOT embedded by the hash of emergency
    and fused as if it were evidence — the vector channel is dropped and the lexical one carries the read."""
    monkeypatch.setattr(emb, "_cloud_embed", _fake_cloud)
    memwriter.insert_memory("Prefiere el té verde.", level="long", kind="pref")
    memreembed.stamp()
    monkeypatch.setattr(emb, "_cloud_embed", lambda texts, *, timeout=None: None)
    calls = []
    monkeypatch.setattr(memret, "vec_search", lambda *a, **k: calls.append("vec") or [])
    hits = memret.search("té verde", k=10, limit=5)
    assert hits, "the lexical channel answers"
    assert calls == [], "a query embedded by the emergency hash is worse than no vector channel at all"
