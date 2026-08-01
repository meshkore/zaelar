"""Regresión de los cambios de ESCRITURA/CONSOLIDACIÓN del 2026-07-12 (buffer conv sin vector + trivia ampliada).

Cambios que blindan estos tests (pedidos por el operador):
  (a) el buffer conversacional (`kind='conv'`) se sigue LEYENDO por recencia (`recent_short`) — el último turno
      siempre visible aunque ya no se embeba.
  (b) un hecho DURABLE se sigue EMBEBIENDO (tiene fila en `vec_memories`) y es recuperable por vector; un `conv`
      NO se embebe (sin fila vec) — a propósito (memory/writer.py, 2026-07-12).
  (c) muletillas ("ah/eh/mmm/vale/ya está/bueno/…") se clasifican como DESCARTE (`classify.level is None`) → no
      generan escritura durable ni corren el procesador LLM.

BD aislada por test (tmp_path + backend hash) — NUNCA toca el perfil real.
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


# ── (a) recencia ve el último turno conv ─────────────────────────────────────────────────────────────────────
def test_recent_short_sees_last_conv_turn(fresh_db):
    memapi.write_now("Operador: qué tiempo hace · zaelar: soleado", level="short", kind="conv")
    last = memapi.write_now("Operador: pon música · zaelar: vale", level="short", kind="conv")
    texts = [m["text"] for m in memapi.recent_short(limit=30)]
    assert any("pon música" in t for t in texts), "el último turno conv debe verse por recencia"
    assert last is not None


# ── (b) durable SÍ se embebe (vector) · conv NO ──────────────────────────────────────────────────────────────
def test_durable_embedded_and_retrievable_conv_not(fresh_db):
    durable = memapi.write_now("El perro del operador se llama Toby.", level="long", kind="fact")
    conv = memapi.write_now("Operador: hola · zaelar: hola", level="short", kind="conv")

    assert _vec_has(durable), "un hecho durable DEBE tener embedding (fila en vec_memories)"
    assert not _vec_has(conv), "un turno conv NO debe embeberse (sin fila en vec_memories) — cambio 2026-07-12"

    # y el durable se recupera por el retriever (canal vector+FTS)
    res = retriever.search("¿cómo se llama el perro?", limit=10)
    assert any("Toby" in m["text"] for m in res), "el hecho durable debe seguir siendo recuperable"


def test_conv_never_promoted_to_durable(fresh_db):
    """consolidator.promote excluye kind='conv' → un conv jamás sube a mid/long (evita durable sin vector)."""
    from memory import consolidator
    import time
    conv = memapi.write_now("Operador: charla efímera · zaelar: ok", level="short", kind="conv")
    fact = memapi.write_now("El operador vive en Girona.", level="short", kind="fact")
    # fuerza la promoción por edad: crea muy antiguo (created lejano)
    old = int(time.time()) - 10 * 86400
    db = memdb.get_db()
    db.execute("UPDATE memories SET created=? WHERE id IN (?, ?)", (old, conv, fact))
    consolidator.promote()
    lvl_conv = db.query_one("SELECT level FROM memories WHERE id=?", (conv,))["level"]
    lvl_fact = db.query_one("SELECT level FROM memories WHERE id=?", (fact,))["level"]
    assert lvl_conv == "short", "un conv NUNCA se promociona (sigue short hasta caducar por TTL)"
    assert lvl_fact in ("mid", "long"), "un hecho normal SÍ se promociona por edad"


# ── (c) muletillas no generan escritura ──────────────────────────────────────────────────────────────────────
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
    """Control: un HECHO real no debe caer en el descarte de trivia."""
    from nucleo import memory_agent
    res = memory_agent.classify(phrase)
    assert res.get("level") is not None, f"{phrase!r} es un hecho, NO debe descartarse"
