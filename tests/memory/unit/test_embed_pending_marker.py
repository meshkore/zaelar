"""`meta.embed_pending` stores the REASON, never a 1—and anyone querying it must check for absence.

No one tested the FORM of this marker (2026-08-24: zero mentions in `tests/`), and the comment describing it
in `writer.py` said `meta.embed_pending=1` while `_mark_embed_pending` writes the reason string. The lie cost
one diagnosis that same day: I queried the studio databases with
`embed_pending = 1`, it returned **0 pending** on a database with a damaged row, and I nearly reported it as
“clean.” I caught it by checking which predicate the product uses to query (`rem.py`, `IS NOT NULL`).

This is the worst kind of cheap failure: **a query that cannot find anything reports the same as a healthy
database**. It does not fail, does not warn, and its answer is reassuring precisely when there is damage.

So this pins down what a consumer may take for granted:
  · the marker stores the REASON, not a Boolean—if someone “simplifies” it to 1, this turns red;
  · `= 1` is structurally blind, and this is verified by RUNNING it against a genuinely marked row;
  · the reason is readable, because “this pill has no vector” and “it lacks one because the index is sealed
    with another model” lead to different actions.

The comment is not tested (it cannot be). The contract that the comment described incorrectly is tested.
"""
from __future__ import annotations

import json

import pytest

from memory import db as memdb
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _backend_declarado(monkeypatch):
    """The backend is DECLARED; it is not inherited from the environment.

    These cases ask “does the active space match the sealed one?”, so they depend on which one is active—and
    without forcing it, with Ollama on the machine, V2-350 PRESERVES it as `ollama` and the signature matches: `space_ok()`
    returns True and the cases fail for a reason unrelated to them. They passed with
    `ZAELAR_EMBED_BACKEND=hash` in the environment and failed under the official runner, which does not force
    it. The same trap already cost a batch in V2-349."""
    from memory import embeddings as mememb
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setattr(mememb, "_mem_cfg", lambda: {"embed_provider": "hash", "embed_model": ""})
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


def _marca(mid: int) -> object:
    row = memdb.get_db().query_one("SELECT meta FROM memories WHERE id=?", (mid,))
    return json.loads(row["meta"] or "{}").get("embed_pending")


def test_el_marcador_guarda_el_MOTIVO_y_no_un_booleano(fresh_db):
    mid = memwriter.insert_memory("un hecho sin vector", weight=0.5)
    memwriter._mark_embed_pending(memdb.get_db(), mid, "sig_mismatch")

    v = _marca(mid)
    assert v == "sig_mismatch"
    assert not isinstance(v, bool) and v != 1, (
        "si el marcador pasa a ser 1/True, toda consulta `IS NOT NULL` sigue funcionando pero se pierde el "
        "MOTIVO — y «no tiene vector» y «el índice está sellado con otro modelo» piden cosas distintas")


def test_una_consulta_por_IGUAL_A_1_es_CIEGA_y_se_demuestra_corriendola(fresh_db):
    """The real error, reproduced: on a database WITH damage, `= 1` counts zero and `IS NOT NULL` counts one."""
    mid = memwriter.insert_memory("otra sin vector", weight=0.5)
    memwriter._mark_embed_pending(memdb.get_db(), mid, "degraded")

    ciega = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 "
        "AND COALESCE(json_extract(meta,'$.embed_pending'),0)=1")["c"]
    buena = memdb.get_db().query_one(
        "SELECT COUNT(*) c FROM memories WHERE valid=1 "
        "AND json_extract(meta,'$.embed_pending') IS NOT NULL")["c"]

    assert buena == 1, "la fila dañada existe"
    assert ciega == 0, (
        "esta es la trampa entera: la consulta equivocada no falla, contesta CERO — «todo limpio» sobre una "
        "base con daño. Si algún día devolviera 1, este test sobra y el marcador cambió de forma")


def test_los_DOS_motivos_que_escribe_el_writer_son_legibles(fresh_db):
    """These are the reasons produced by `insert_memory` itself; if a third one appears, declare it here."""
    for razon in ("sig_mismatch", "degraded"):
        mid = memwriter.insert_memory(f"pildora {razon}", weight=0.5)
        memwriter._mark_embed_pending(memdb.get_db(), mid, razon)
        assert _marca(mid) == razon


def test_marcar_NUNCA_lanza_aunque_la_fila_no_exista(fresh_db):
    """It runs inside an already completed write: failing here would lose the pill, which was saved correctly."""
    memwriter._mark_embed_pending(memdb.get_db(), 999_999, "sig_mismatch")   # must not raise


# ── V2-484 · permission expired with the BACKEND, not with the clock ───────────────────────────────────────
#
# The 15 vectors from another space in the operator's index (V2-482) entered here, and the race was reproduced
# in full: the verdict from `space_ok()` was cached for 60 s based ONLY on time, so a backend that fell back to
# `hash` within that window wrote with the permission from when Ollama was alive. No marker and no error: the
# row becomes indistinguishable from a healthy one.

@pytest.fixture
def sellado_gemma(tmp_path, monkeypatch):
    """An index that declares a REAL space. The test backend is `hash` → any vector from it is foreign,
    so the guard MUST refuse it unless someone gives it an expired permission."""
    from memory import reembed as memreembed
    (tmp_path / "zaelar.db.embedsig").write_text("ollama:embeddinggemma:768", encoding="utf-8")
    memreembed._SPACE_CACHE = (0.0, True, None)
    # The PRECONDITION is declared, not inherited: if the signature path resolved elsewhere, these cases
    # would measure another database's `.embedsig`, and their passing would mean nothing.
    assert memreembed.stored_signature() == "ollama:embeddinggemma:768"
    yield
    memreembed._SPACE_CACHE = (0.0, True, None)


def _con_ollama_vivo():
    """Warms the cache at the instant when the signature DID match (Ollama responding with embeddinggemma).

    Restores MANUALLY and NOT with `monkeypatch.undo()`: that undoes everything the function has set at that
    moment, **including `fresh_db`'s `ZAELAR_DB`**. With it reverted, `_sig_path()` stops pointing to the test
    database and the guard reads the `.embedsig` from the operator's REAL memory instead—so these cases passed
    alone by reading a foreign signature and failed in the full suite depending on which path they encountered.
    A borrowed pass, once again."""
    from memory import embeddings as mememb
    from memory import reembed as memreembed
    previo = (mememb.active_backend, mememb._active_model_name, mememb._backend)
    mememb.active_backend = lambda: "ollama"
    mememb._active_model_name = lambda: "embeddinggemma"
    mememb._backend = "ollama"
    try:
        assert memreembed.space_ok() is True
    finally:
        mememb.active_backend, mememb._active_model_name, mememb._backend = previo


def test_el_permiso_NO_sobrevive_a_una_caida_del_backend(fresh_db, sellado_gemma, monkeypatch):
    from memory import embeddings as mememb
    from memory import reembed as memreembed
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "hash")          # seconds later, within the TTL
    assert memreembed.space_ok() is False


def test_un_vector_de_otro_espacio_NO_se_escribe_con_el_permiso_de_antes(fresh_db, sellado_gemma, monkeypatch):
    """The COMPLETE race through the real write path—the one that left 15 damaged, silent rows."""
    from memory import embeddings as mememb
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "hash")
    mid = memwriter.insert_memory("Le interesan los Ferrari.", level="long", kind="pref")
    fila = memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,))
    assert fila is None                                      # no vector: better none than one from another space
    assert _marca(mid) == "sig_mismatch"                      # and COUNTABLE, which was what was missing


def test_el_guarda_decide_DESPUES_de_saber_en_que_espacio_salio_el_vector(fresh_db, sellado_gemma, monkeypatch):
    """The switch WITHIN the same call: backend resolution occurs inside `_emb.embed()`, that is,
    AFTER the first check. Without the second one, that vector enters with permission already granted.

    It deliberately uses a SLOT, and this was hard to find: without a slot, `insert_memory` queries
    `_semantic_dedup_on()` first, which resolves the backend independently—so the switch occurs BEFORE the first
    guard and that guard catches it. With a slot, that step is skipped and the backend is still the good one when
    the entry guard looks. Measured both ways: with the second check the vector is refused; without it, it is
    written without a marker. A case without a slot would have passed with the fix DISARMED."""
    from memory import embeddings as mememb
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "ollama")        # the ENTRY guard still sees the good space

    def _embed_que_cae(_t):
        mememb._backend = "hash"                             # Ollama busy AND fastembed not loaded
        return mememb._l2_normalize(mememb._fit_dim(mememb._hash_embed(_t, 768), 768))

    monkeypatch.setattr(mememb, "embed", _embed_que_cae)
    monkeypatch.setattr(mememb, "last_degraded", False)      # CONFIGURED hash is not declared degraded
    mid = memwriter.insert_memory("Le gusta la guitarra.", level="long", kind="pref", slot="operator.tastes")
    assert memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,)) is None
    assert _marca(mid) == "sig_mismatch"


def test_con_el_espacio_ESTABLE_el_camino_sano_no_cambia(fresh_db, monkeypatch):
    """The other half: without a sealed signature (new database), the vector continues to be written as usual.
    A guard that also stopped this would not be safer; it would be a database without a semantic channel."""
    mid = memwriter.insert_memory("Vive en Madrid.", level="long", kind="fact")
    assert memdb.get_db().query_one("SELECT 1 FROM vec_memories WHERE memory_id=?", (mid,)) is not None
    assert _marca(mid) is None


# ── V2-485 · the concept node wrote its vector WITHOUT any guard ────────────────────────────────────────────
#
# Neither race nor stale permission: `_get_or_create_concept` inserted into `vec_memories` without checking the
# signature or degradation. The 9 fastembed vectors (384 padded to 768) from the operator's index entered there,
# all concept nodes. The node must still be created—it is a graph hub—and its vector is what is deferred.

def _concepto(nombre: str):
    return memdb.get_db().query_one(
        "SELECT id FROM memories WHERE kind='concept' AND lower(text)=? LIMIT 1", (nombre,))


def test_un_concepto_NO_recibe_vector_de_otro_espacio(fresh_db, sellado_gemma, monkeypatch):
    from memory import embeddings as mememb
    _con_ollama_vivo()
    monkeypatch.setattr(mememb, "_backend", "hash")          # the index says gemma, but the backend no longer does
    memwriter.insert_memory("Toca la guitarra.", level="long", kind="fact", concepts=["guitarra"])
    c = _concepto("guitarra")
    assert c is not None                                     # the HUB is still created: without it the graph cannot connect
    assert memdb.get_db().query_one(
        "SELECT 1 FROM vec_memories WHERE memory_id=?", (c["id"],)) is None
    assert _marca(c["id"]) == "sig_mismatch"                 # and remains COUNTABLE for the sleeper


def test_un_concepto_NO_recibe_vector_de_un_backend_caido_en_caliente(fresh_db, monkeypatch):
    """The other half of the gate: `last_degraded` was also missing from this path.

    The flag is set INSIDE `embed_batch`, so setting it beforehand is useless—the call recalculates it itself.
    This is simulated as it really happens: the failure is declared while producing the vector."""
    from memory import embeddings as mememb

    def _embed_que_se_cae(t):
        mememb.last_degraded = True                          # real backend failed live → emergency hash
        return mememb._l2_normalize(mememb._fit_dim(mememb._hash_embed(t, 768), 768))

    monkeypatch.setattr(mememb, "embed", _embed_que_se_cae)
    memwriter.insert_memory("Le gusta el pádel.", level="long", kind="fact", concepts=["deporte"])
    c = _concepto("deporte")
    assert c is not None
    assert memdb.get_db().query_one(
        "SELECT 1 FROM vec_memories WHERE memory_id=?", (c["id"],)) is None
    assert _marca(c["id"]) == "degraded"


def test_con_el_espacio_sano_el_concepto_SI_recibe_su_vector(fresh_db):
    """Without this, “do not write bad vectors” is satisfied by writing none—and a concept without a vector
    cannot be found by a category query, which is what the node exists for."""
    memwriter.insert_memory("Le gusta el buceo.", level="long", kind="fact", concepts=["ocio"])
    c = _concepto("ocio")
    assert c is not None
    assert memdb.get_db().query_one(
        "SELECT 1 FROM vec_memories WHERE memory_id=?", (c["id"],)) is not None
    assert _marca(c["id"]) is None
