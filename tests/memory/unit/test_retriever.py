"""Tests de memory/retriever.py (V2-002 · T47) — fusión RRF, score ponderado, graph_expand."""
import time

import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import retriever as memret
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


def test_rrf_fuses_ranks():
    # id 2 es el mejor (rank 1) en AMBAS listas → mayor score fusionado.
    a = [(2, 0.1), (1, 0.2), (3, 0.3)]
    b = [(2, 5.0), (1, 6.0)]
    fused = memret.rrf(a, b, k=60)
    assert max(fused, key=fused.get) == 2
    assert fused[1] > fused[3]  # 1 está en ambas listas; 3 solo en una


def test_query_finds_relevant_by_keyword(fresh_db):
    memwriter.insert_memory("el operador se llama Ricart y vive en Barcelona", kind="fact", level="long")
    memwriter.insert_memory("la receta del bizcocho lleva harina, huevos y azúcar", kind="event")
    res = memret.search("¿dónde vive Ricart?", limit=5, expand=False)
    assert res, "debe devolver algo"
    assert "Ricart" in res[0]["text"]


def test_query_empty_db_returns_empty(fresh_db):
    # sin recuerdos, no hay candidatos (el recall vectorial devuelve vecinos SOLO si existen filas).
    res = memret.search("cualquier cosa", limit=5, expand=False)
    assert res == []


def test_score_weights_importance_and_recency(fresh_db):
    now = int(time.time())
    # dos recuerdos que casan el mismo keyword; uno más importante + más reciente
    hi = memwriter.insert_memory("proyecto Colmena importante", kind="fact", level="long")  # imp 0.7
    lo = memwriter.insert_memory("proyecto Colmena trivial", kind="msg")                    # imp 0.4
    # envejecer el 'lo' para bajar su recencia
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now - 40 * 86400, lo))
    memdb.get_db().execute("UPDATE memories SET last_access=? WHERE id=?", (now, hi))
    res = memret.search("proyecto Colmena", limit=5, expand=False)
    ids = [r["id"] for r in res]
    assert ids.index(hi) < ids.index(lo)


def test_graph_expand_pulls_neighbors(fresh_db):
    a = memwriter.insert_memory("tema central sobre Wallapop", kind="fact", level="long")
    b = memwriter.insert_memory("dato colateral vinculado", kind="event")
    memwriter.link(a, b, "about", 1.0)
    # unidad: graph_expand añade el vecino b a un conjunto que solo trae a.
    seed = [{"id": a, "text": "tema central sobre Wallapop", "score": 1.0, "weight": 0.5,
             "importance": 0.7, "last_access": None}]
    expanded = memret.graph_expand(seed)
    ids = [r["id"] for r in expanded]
    assert b in ids
    vb = next(r for r in expanded if r["id"] == b)
    assert vb.get("via", "").startswith("edge:")
    assert vb["score"] < seed[0]["score"]  # score descontado


def test_reinforce_signal_emitted(fresh_db):
    import bus
    got = {}

    def sink(rec):
        if rec["topic"] == "memory.reinforce":
            got["ids"] = rec["payload"]["ids"]

    bus.add_sink(sink)
    try:
        memwriter.insert_memory("recuerdo reforzable", kind="fact")
        memret.search("recuerdo reforzable", limit=5, expand=False, reinforce=True)
        assert "ids" in got and len(got["ids"]) >= 1
    finally:
        bus.remove_sink(sink)


# V2-031 T2 (2026-08-17): índice de paráfrasis — un memory_id debe aparecer en `search()` cuando la QUERY casa
# con una de sus reformulaciones aunque comparta poco vocabulario con el texto original de la píldora.
def test_vec_search_paraphrases_maps_back_to_real_memory_id(fresh_db):
    mid = memwriter.insert_memory("toca la guitarra los sábados por la tarde", kind="fact", level="mid")
    memwriter.index_paraphrases(mid, ["es un músico aficionado"])
    from memory import embeddings as _emb
    qvec = _emb.embed("es un músico aficionado")
    hits = memret.vec_search_paraphrases(qvec, k=10)
    assert any(m == mid for m, _ in hits)


def test_search_surfaces_pill_via_paraphrase_vocab_gap(fresh_db):
    mid = memwriter.insert_memory("toca la guitarra los sábados por la tarde", kind="fact", level="mid")
    other = memwriter.insert_memory("cocina platos italianos los domingos", kind="fact", level="mid")
    memwriter.index_paraphrases(mid, ["es un músico aficionado"])
    results = memret.search("es un músico aficionado", limit=5, expand=False, rerank=False)
    ids = [r["id"] for r in results]
    assert mid in ids
    assert other not in ids or ids.index(mid) < ids.index(other)


def test_search_never_returns_a_bare_concept_node(monkeypatch, tmp_path):
    """V2-114 F4.1 — un nodo-concepto es SEMILLA de expansión, no respuesta. Su `text` es la palabra del
    concepto («familia»), así que devolverlo gasta un hueco del top-3 con cero información. `graph_expand` los
    necesita presentes para promocionar su cluster (T126), de ahí que el filtro vaya DESPUÉS de expandir: este
    test fija que el resultado FINAL no los lleve, sin impedir que sigan sirviendo de semilla."""
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "z.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    from memory import db as _db
    _db.reset_db()
    _db.get_db()
    from memory import api as memapi
    from memory import retriever as _ret

    # Un hecho REAL sobre la familia + su nodo-concepto (lo crea el writer al enlazar conceptos).
    memapi.write_now("Su hermana se llama Marta y vive en Madrid.", level="long", kind="fact",
                     importance=0.7, concepts=["familia"])
    res = _ret.search("¿qué sabes de mi familia?", limit=10, expand=True, reinforce=False)

    assert res, "la búsqueda debe devolver algo (el hecho existe)"
    assert all(r.get("kind") != "concept" for r in res), \
        f"un nodo-concepto se coló en el resultado: {[r['text'] for r in res if r.get('kind') == 'concept']}"
    _db.reset_db()


# ── a query embedded in the WRONG SPACE is worse than no vector channel (2026-08-18) ─────────────────────────
# The write path has refused to insert a vector on a space mismatch since V2-103; the READ path had no
# equivalent check and fused pure noise into the RRF. Reproduced in production: a transient Ollama 503 latches
# the process onto `fastembed` for 300s, and every recall in that window searches embeddinggemma vectors with a
# bge-small query. FTS keeps working, so the symptom is not an error — it is "recall got a bit worse today".
def test_search_drops_the_vector_channels_when_the_space_does_not_match(fresh_db, monkeypatch):
    memwriter.insert_memory("mi perro se llama Toby", level="long", kind="fact")

    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "space_ok", lambda *a, **k: False)

    llamadas = {"vec": 0, "para": 0, "fts": 0}
    orig_vec, orig_para, orig_fts = memret.vec_search, memret.vec_search_paraphrases, memret.fts_search
    monkeypatch.setattr(memret, "vec_search",
                        lambda *a, **k: (llamadas.__setitem__("vec", llamadas["vec"] + 1), orig_vec(*a, **k))[1])
    monkeypatch.setattr(memret, "vec_search_paraphrases",
                        lambda *a, **k: (llamadas.__setitem__("para", llamadas["para"] + 1), orig_para(*a, **k))[1])
    monkeypatch.setattr(memret, "fts_search",
                        lambda *a, **k: (llamadas.__setitem__("fts", llamadas["fts"] + 1), orig_fts(*a, **k))[1])

    out = memret.search("Toby", rerank=False)
    assert llamadas["vec"] == 0, "no se puede buscar con un vector del espacio equivocado"
    assert llamadas["para"] == 0, "el canal de paráfrasis usa el MISMO vector de consulta: también fuera"
    assert llamadas["fts"] == 1, "el canal léxico no depende de ningún espacio: tiene que seguir cargando la lectura"
    assert any("Toby" in r["text"] for r in out), "degradar a FTS no puede significar devolver nada"


def test_search_uses_the_vector_channels_when_the_space_matches(fresh_db, monkeypatch):
    """La otra mitad: sin esto, un guard que apagara los canales SIEMPRE también pasaría el test de arriba."""
    memwriter.insert_memory("mi perro se llama Toby", level="long", kind="fact")

    from memory import reembed as memreembed
    monkeypatch.setattr(memreembed, "space_ok", lambda *a, **k: True)

    vistos = {"vec": 0}
    orig_vec = memret.vec_search
    monkeypatch.setattr(memret, "vec_search",
                        lambda *a, **k: (vistos.__setitem__("vec", vistos["vec"] + 1), orig_vec(*a, **k))[1])
    memret.search("Toby", rerank=False)
    assert vistos["vec"] == 1
