"""Regression coverage for the 2026-07-12 WRITE/CONSOLIDATION changes (conv buffer without vector + expanded trivia).

Changes that these tests lock down (requested by the operator):
  (a) the conversational buffer (`kind='conv'`) continues to be READ by recency (`recent_short`) — the latest turn
      is always visible even when it is no longer embedded.
  (b) a DURABLE fact continues to be EMBEDDED (it has a row in `vec_memories`) and is retrievable by vector; a `conv`
      is NOT embedded (no vec row) — intentionally (memory/writer.py, 2026-07-12).
  (c) filler words ("ah/eh/mmm/vale/ya está/bueno/…") are classified as DISCARD (`classify.level is None`) → they do not
      generate durable writes or run the LLM processor.

Database isolated per test (tmp_path + hash backend) — NEVER touches the real profile.
"""
import pytest

from memory import api as memapi
from memory import db as memdb
from memory import embeddings as mememb
from memory import retriever


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


def _vec_has(mid: int) -> bool:
    db = memdb.get_db()
    if not db.vec_available:
        pytest.skip("sqlite-vec no disponible")
    return db.query_one("SELECT COUNT(*) c FROM vec_memories WHERE memory_id=?", (mid,))["c"] > 0


# ── (a) recency sees the latest conv turn ─────────────────────────────────────────────────────────────────────
def test_recent_short_sees_last_conv_turn(fresh_db):
    memapi.write_now("Operador: qué tiempo hace · zaelar: soleado", level="short", kind="conv")
    last = memapi.write_now("Operador: pon música · zaelar: vale", level="short", kind="conv")
    texts = [m["text"] for m in memapi.recent_short(limit=30)]
    assert any("pon música" in t for t in texts), "el último turno conv debe verse por recencia"
    assert last is not None


# ── (b) durable IS embedded (vector) · conv is NOT ──────────────────────────────────────────────────────────
def test_durable_embedded_and_retrievable_conv_not(fresh_db):
    durable = memapi.write_now("El perro del operador se llama Toby.", level="long", kind="fact")
    conv = memapi.write_now("Operador: hola · zaelar: hola", level="short", kind="conv")

    assert _vec_has(durable), "un hecho durable DEBE tener embedding (fila en vec_memories)"
    assert not _vec_has(conv), "un turno conv NO debe embeberse (sin fila en vec_memories) — cambio 2026-07-12"

    # and the durable item is retrieved by the retriever (vector+FTS channel)
    res = retriever.search("¿cómo se llama el perro?", limit=10)
    assert any("Toby" in m["text"] for m in res), "el hecho durable debe seguir siendo recuperable"


def test_conv_never_promoted_to_durable(fresh_db):
    """consolidator.promote excludes kind='conv' → a conv never advances to mid/long (avoids a durable item without a vector)."""
    from memory import consolidator
    import time
    conv = memapi.write_now("Operador: charla efímera · zaelar: ok", level="short", kind="conv")
    fact = memapi.write_now("El operador vive en Girona.", level="short", kind="fact")
    # force age-based promotion: make it very old (distant created timestamp)
    old = int(time.time()) - 10 * 86400
    db = memdb.get_db()
    db.execute("UPDATE memories SET created=? WHERE id IN (?, ?)", (old, conv, fact))
    consolidator.promote()
    lvl_conv = db.query_one("SELECT level FROM memories WHERE id=?", (conv,))["level"]
    lvl_fact = db.query_one("SELECT level FROM memories WHERE id=?", (fact,))["level"]
    assert lvl_conv == "short", "un conv NUNCA se promociona (sigue short hasta caducar por TTL)"
    assert lvl_fact in ("mid", "long"), "un hecho normal SÍ se promociona por edad"


# ── (c) filler words do not generate writes ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("phrase", [
    "ah", "eh", "mmm", "hmm", "vale", "ya está", "bueno", "venga", "nada", "okey", "claro", "ajá",
])
def test_trivia_is_discarded(phrase):
    from nucleo import memory_agent
    res = memory_agent.classify(phrase)
    assert res.get("level") is None, f"{phrase!r} debe descartarse (level None), no escribirse"


@pytest.mark.parametrize("phrase", [
    "El perro se llama Toby",
    "Vivo en Girona",
    "Trabajo en un proyecto que se llama zaelar",
])
def test_real_fact_is_not_discarded(phrase):
    """Control: a real FACT must not be discarded as trivia."""
    from nucleo import memory_agent
    res = memory_agent.classify(phrase)
    assert res.get("level") is not None, f"{phrase!r} es un hecho, NO debe descartarse"
