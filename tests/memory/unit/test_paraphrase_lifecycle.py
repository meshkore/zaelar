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


# ── the raw utterance as a second retrieval path: BUILT, MEASURED, REMOVED (V2-114 F4.2, 2026-08-19) ──────────
# The mechanism is gone from `memory/writer.py` (see the epitaph there for the full numbers). It lost on BOTH
# corpora and, on LoCoMo, lost precisely where it was designed to win: temporal did not move and single-hop
# dropped 7.2pp, plus +48% read latency and ~2x the database. Its tests went with it rather than being kept green
# against nothing.
#
# What SURVIVES here is the paraphrase lifecycle above: `index_paraphrases`/`drop_paraphrases` carry
# REM-generated paraphrases, a different mechanism that was mute from the day it was built and is now verified
# working (F4.3). The deletion of one must not quietly take the other's coverage with it, which is why this file
# still exists and this comment says so.
