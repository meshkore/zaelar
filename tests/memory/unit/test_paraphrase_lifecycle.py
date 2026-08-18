"""A paraphrase must die with its pill (2026-08-18, V2-114 F4.2 groundwork).

`paraphrase_index`/`vec_paraphrases` were built in V2-031 T2 and, because the channel was MUTE from day one
(`nucleo/memllm._DEFAULTS` left reasoning on, so the generator always returned empty), nothing ever exercised
their deletion. Turning the channel on made two latent defects real, and the first one is not hygiene:

  1. RIGHT TO BE FORGOTTEN. `forget(hard=True)` deleted the `memories` row, its vector, its FTS entry and its
     edges — and left the operator's datum sitting VERBATIM in `paraphrase_index.text`.
  2. ORPHANS THAT KEEP MATCHING. `vec_paraphrases` is keyed by the synthetic PK, so vectors survive their
     memory and keep winning KNN slots, mapping back to an id that no longer exists.

Two paths touch this: `writer.delete_memory` (the real deletion, right to be forgotten) and
`consolidator.prune_invalid` (de-indexes a superseded shell, keeping its row — history is never deleted). Both
are covered here, because a fix applied to one of two paths is the same bug with a smaller blast radius.
"""
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


def _counts():
    db = memdb.get_db()
    pi = db.query_one("SELECT COUNT(*) c FROM paraphrase_index")["c"]
    vp = db.query_one("SELECT COUNT(*) c FROM vec_paraphrases")["c"] if db.vec_available else 0
    return pi, vp


def test_hard_delete_takes_the_paraphrase_text_with_it(fresh_db):
    mid = memwriter.insert_memory("mi cuenta es ES12 3456 7890", level="long", kind="fact")
    assert memwriter.index_paraphrases(mid, ["el numero de cuenta bancaria del operador"]) == 1
    assert _counts() == (1, 1)

    memwriter.delete_memory(mid)

    assert _counts() == (0, 0), (
        "un olvido DURO que deja la paráfrasis en la tabla no ha borrado el dato: la paráfrasis es una "
        "reescritura del propio dato del operador"
    )


def test_pruning_a_superseded_shell_also_de_indexes_its_paraphrases(fresh_db):
    """`prune_invalid` es el OTRO camino, y no borra la fila: la saca de los ÍNDICES (el histórico se conserva a
    propósito). Es literalmente el defecto que P2-6 arregló para vec+FTS en 2026-07-19, una tabla más tarde —
    la cáscara muerta sigue ganando huecos del KNN y apunta a una fila `valid=0` que el lector descarta, o sea
    presupuesto de pool gastado en muertos. No se ve al leer; se ve meses después como «el recall ha empeorado»."""
    mid = memwriter.insert_memory("dato prescindible", level="long", kind="fact", weight=0.01)
    memwriter.index_paraphrases(mid, ["otra forma de decir el dato prescindible"])
    assert _counts() == (1, 1)

    # invalidar + pasar la poda de inválidos, que es el camino de borrado duro del sueño
    memwriter.supersede(mid, mid)          # marca valid=0 (supersede a sí mismo: solo queremos invalidar)
    # `now` en el futuro en vez de `after_days=0`: el corte es `updated < now - after_days*86400`, y la fila
    # acaba de actualizarse, así que con 0 días no entra en su propia poda.
    from memory.clock import now as _now
    memcons.prune_invalid(now=_now() + 3600, after_days=0)

    pi, vp = _counts()
    assert (pi, vp) == (0, 0), f"quedaron {pi} filas y {vp} vectores de paráfrasis indexados tras la poda"


def test_drop_paraphrases_is_a_noop_for_a_pill_without_any(fresh_db):
    mid = memwriter.insert_memory("dato sin paráfrasis", level="long", kind="fact")
    assert memwriter.drop_paraphrases(mid) == 0
    assert memwriter.drop_paraphrases(0) == 0


def test_drop_paraphrases_only_touches_its_own_pill(fresh_db):
    a = memwriter.insert_memory("dato A", level="long", kind="fact")
    b = memwriter.insert_memory("dato B", level="long", kind="fact")
    memwriter.index_paraphrases(a, ["otra forma de A"])
    memwriter.index_paraphrases(b, ["otra forma de B"])
    assert _counts() == (2, 2)

    assert memwriter.drop_paraphrases(a) == 1
    pi, vp = _counts()
    assert (pi, vp) == (1, 1)
    db = memdb.get_db()
    assert db.query_one("SELECT memory_id FROM paraphrase_index")["memory_id"] == b


# ── the raw utterance as a SECOND retrieval path to the distilled pill (V2-114 F4.2) ─────────────────────────
# Measured on LoCoMo with our own pipeline: distilling wins multi-hop (+12.6pp) and open-domain (+15.4pp) and
# LOSES temporal (-8.1pp) and single-hop (-2.8pp), because a date said once lives in the literal wording. So the
# pill stays the answer and the raw utterance becomes a way to find it — augment, never replace.
def test_a_durable_pill_indexes_the_operators_own_words(fresh_db):
    mid = memwriter.insert_memory("Su perro se llama Toby y es un labrador.", level="long", kind="fact",
                                  meta={"raw": "mi perro se llama Toby, es un labrador precioso"})
    db = memdb.get_db()
    rows = db.query("SELECT memory_id, text FROM paraphrase_index")
    assert len(rows) == 1 and rows[0]["memory_id"] == mid
    assert rows[0]["text"] == "mi perro se llama Toby, es un labrador precioso"
    assert db.query_one("SELECT COUNT(*) c FROM vec_paraphrases")["c"] == 1


def test_raw_identical_to_the_pill_is_not_indexed_twice(fresh_db):
    """When the distiller is down the heuristic stores the utterance nearly verbatim. A second copy of the same
    sentence buys no retrieval surface and doubles this pill's footprint in the vector table."""
    memwriter.insert_memory("dato igual", level="long", kind="fact", meta={"raw": "  Dato Igual  "})
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM paraphrase_index")["c"] == 0


def test_short_term_pills_do_not_get_a_raw_path(fresh_db):
    """Short-term memories expire and are read by an over-inclusive path that never touches the retriever —
    indexing them would pay the cost with no reader to benefit."""
    memwriter.insert_memory("efímero", level="short", kind="event", meta={"raw": "otra frase efímera distinta"})
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM paraphrase_index")["c"] == 0


def test_raw_indexing_has_a_kill_switch(fresh_db, monkeypatch):
    monkeypatch.setattr(memwriter, "_RAW_INDEXING", False)
    memwriter.insert_memory("Su perro se llama Toby.", level="long", kind="fact",
                            meta={"raw": "mi perro se llama Toby"})
    assert memdb.get_db().query_one("SELECT COUNT(*) c FROM paraphrase_index")["c"] == 0
