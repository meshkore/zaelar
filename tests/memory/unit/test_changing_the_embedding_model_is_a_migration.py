"""Changing the embedding model is a MIGRATION, not a failover (V2-824).

The vectors in `zaelar.db` live in the space of the model that produced them. When the ACTIVE model changes on
purpose (the panel, a profile), the one door `memory/reembed.migrate` has to: re-embed every pill AND every
paraphrase in the new space, reseal `<db>.embedsig`, leave no foreign vector behind, and clear the markers of
rows that now carry a vector. And the other half of the rule: an existing database keeps its sealed space until
the user changes the model on purpose — a boot that merely FINDS the signatures apart warns and does nothing.

Two deterministic spaces stand in for two models: `hash` (the test backend) and a fake cloud model whose
vectors are the hash vectors REVERSED — same width, different geometry, trivially distinguishable.
"""
from __future__ import annotations

import json

import pytest

from memory import db as memdb
from memory import embeddings as emb
from memory import reembed as memreembed
from memory import rem as memrem
from memory import writer as memwriter

_DIM = 768


def _hash_vec(t: str) -> list[float]:
    return emb._l2_normalize(emb._fit_dim(emb._hash_embed(t, _DIM), _DIM))


def _other_space(texts, *, timeout=None):
    """The 'new model': the hash vector shifted by a constant and renormalised — DENSE (a real embedding never
    ends in hundreds of zeros, and `rem._looks_padded` rightly treats a sparse one as foreign), deterministic,
    768 wide, and nowhere near the hash vector of the same text."""
    return [emb._l2_normalize([x + 0.05 for x in _hash_vec(t)]) for t in texts]


@pytest.fixture(autouse=True)
def _declared(monkeypatch):
    monkeypatch.setenv("MEM_SEMANTIC_DEDUP", "0")
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)
    yield
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _use_hash(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)


def _use_new_model(monkeypatch):
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai", "embed_model": "text-embedding-3-small"})
    monkeypatch.setattr(emb, "_cloud_embed", _other_space)
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)


def _vector(mid: int):
    row = memdb.get_db().query_one("SELECT embedding FROM vec_memories WHERE memory_id=?", (mid,))
    return memrem._unpack(row["embedding"]) if row else None


def _marker(mid: int):
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    return json.loads(row["meta"] or "{}").get("embed_pending")


def _seed(monkeypatch) -> list[int]:
    """Three pills + a paraphrase, sealed in the hash space."""
    _use_hash(monkeypatch)
    ids = [memwriter.insert_memory(t, level="long", kind="fact") for t in
           ("Su hermana vive en Lugo.", "Toca el piano los domingos.", "Le gusta el cine coreano.")]
    assert memwriter.index_paraphrases(ids[2], ["Disfruta de las películas de Corea."]) == 1
    memreembed.stamp()
    assert memreembed.stored_signature() == "hash:hash:768"
    return ids


def test_the_whole_memory_moves_to_the_new_space_and_the_seal_follows(fresh_db, monkeypatch):
    ids = _seed(monkeypatch)
    old_vectors = {i: _vector(i) for i in ids}
    memwriter._mark_embed_pending(memdb.get_db(), ids[0], "degraded")   # a stale marker from an old outage

    _use_new_model(monkeypatch)
    rep = memreembed.migrate(reason="test")

    assert rep["ok"] and rep["action"] == "migrated", rep
    assert rep["from"] == "hash:hash:768" and rep["to"] == "cloud:text-embedding-3-small:768"
    valid = memdb.get_db().query_one("SELECT COUNT(*) c FROM memories WHERE valid=1")["c"]
    assert rep["reindexed"] == valid >= 3 and rep["paraphrases"] == 1, rep
    assert memreembed.stored_signature() == "cloud:text-embedding-3-small:768", "the seal follows the space"
    texts = {r["id"]: r["text"] for r in memdb.get_db().query("SELECT id, text FROM memories")}
    for i in ids:
        v = _vector(i)
        assert v is not None
        assert v == pytest.approx(_other_space([texts[i]])[0]), "every vector is the NEW model's"
        assert v != pytest.approx(old_vectors[i]), "and none of the old space survived"
    para = memdb.get_db().query_one("SELECT p.id, p.text, v.embedding FROM paraphrase_index p "
                                    "JOIN vec_paraphrases v ON v.id = p.id")
    assert para is not None, "the paraphrase channel was re-embedded too, not left in the old space"
    assert memrem._unpack(para["embedding"]) == pytest.approx(_other_space([para["text"]])[0])
    assert rep["foreign_left"] == 0 and memrem._drop_foreign_vectors(memdb.get_db(), 100) == 0
    assert _marker(ids[0]) is None and rep["pending_cleared"] == 1, "a row with a vector carries no marker"
    # and the writer now accepts vectors again: the space is coherent
    new = memwriter.insert_memory("Colecciona sellos.", level="long", kind="pref")
    assert _vector(new) is not None and _marker(new) is None


def test_an_existing_database_keeps_its_space_until_the_model_is_changed_ON_PURPOSE(fresh_db, monkeypatch):
    """`check()` at boot finds the signatures apart: it WARNS and touches nothing. The writer keeps deferring
    (sig_mismatch) rather than writing into the wrong space. Only `migrate()` moves it."""
    ids = _seed(monkeypatch)
    _use_new_model(monkeypatch)
    out = memreembed.check()
    assert out["ok"] is False and out["action"] == "reembed_needed"
    assert memreembed.stored_signature() == "hash:hash:768", "a boot never rewrites the memory"
    assert _vector(ids[0]) == pytest.approx(_hash_vec("Su hermana vive en Lugo."))
    deferred = memwriter.insert_memory("Juega al pádel.", level="long", kind="pref")
    assert _vector(deferred) is None and _marker(deferred) == "sig_mismatch"


def test_the_same_model_is_not_a_migration(fresh_db, monkeypatch):
    _seed(monkeypatch)
    rep = memreembed.migrate(reason="nothing moved")
    assert rep["action"] == "none" and rep["ok"]
    assert memreembed.stored_signature() == "hash:hash:768"


def test_a_degraded_new_model_aborts_WITHOUT_resealing(fresh_db, monkeypatch):
    """Half a migration is worse than none: the provider dies mid-way, the old seal stays, the report says so."""
    _seed(monkeypatch)
    monkeypatch.setattr(emb, "_mem_cfg", lambda: {"embed_provider": "openai", "embed_model": "text-embedding-3-small"})
    monkeypatch.setattr(emb, "_cloud_embed", lambda texts, *, timeout=None: None)
    emb.reset()
    memreembed._SPACE_CACHE = (0.0, True, None)
    rep = memreembed.migrate(reason="dead key")
    assert rep["ok"] is False and rep["action"] == "aborted"
    assert memreembed.stored_signature() == "hash:hash:768", "the seal never names a space the index is not in"


def test_an_empty_database_is_only_stamped(fresh_db, monkeypatch):
    _use_new_model(monkeypatch)
    (memdb.db_path().with_suffix(memdb.db_path().suffix + ".embedsig")).write_text("hash:hash:768")
    rep = memreembed.migrate(reason="fresh")
    assert rep["action"] == "stamped" and memreembed.stored_signature() == "cloud:text-embedding-3-small:768"


# ── the doors that fire it ────────────────────────────────────────────────────────────────────────────────────

def test_the_panel_fires_the_migration_only_when_a_space_key_changes(tmp_path, monkeypatch):
    import config.v2 as v2
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from server import config_api
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    # The effective value is store > env > table: an env var another test left behind would already BE the new
    # value, and «nothing moved» would be the right answer to a question this test is not asking.
    for k in ("ZAELAR_EMBED_BACKEND", "ZAELAR_EMBED_MODEL", "ZAELAR_EMBED_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    fired = []
    monkeypatch.setattr(config_api, "_start_embedding_migration", lambda moved: fired.append(moved) or {"started": True})
    app = FastAPI()
    app.include_router(config_api.router)
    client = TestClient(app)

    r = client.post("/api/config/v2", json={"section": "memory", "patch": {"rerank_top_n": 25}})
    assert r.json()["ok"] and fired == [], "a knob that does not move the space migrates nothing"

    r = client.post("/api/config/v2", json={"section": "memory",
                                            "patch": {"embed_provider": "ollama", "embed_model": "embeddinggemma"}})
    body = r.json()
    assert body["ok"] and body.get("embedding_migration", {}).get("started"), body
    assert fired and set(fired[0]) == {"embed_provider", "embed_model"}

    r = client.post("/api/config/v2", json={"section": "memory", "patch": {"embed_model": "embeddinggemma"}})
    assert r.json()["ok"] and len(fired) == 1, "writing the same value again is not a change"


def test_a_profile_that_moves_the_space_migrates_through_the_same_door(tmp_path, monkeypatch):
    import config.profiles as profiles
    import config.settings as settings
    import config.v2 as v2
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    monkeypatch.setattr(settings, "effective", lambda: {"knobs": [], "free_text": [], "voices_by_provider": {}})
    calls = []
    monkeypatch.setattr(memreembed, "migrate", lambda *, reason="": calls.append(reason) or {"ok": True, "action": "none"})

    res = profiles.apply("local")                       # cloud titular → ollama: the space moves
    assert res["applied"].get("embedding_migration") == {"ok": True, "action": "none"} and calls == ["profile local"]
    profiles.apply("local")                             # same again: nothing moves
    assert calls == ["profile local"]
    profiles.apply("cloud")                             # back: moves again
    assert calls == ["profile local", "profile cloud"]
