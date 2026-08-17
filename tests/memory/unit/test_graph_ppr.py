"""tests/memory/unit/test_graph_ppr.py — Personalized PageRank sobre `edges` (V2-111 §9.1).

`graph_expand()` (1-hop) no alcanza una conexión de 2 saltos por diseño; estos tests prueban primero el
módulo puro (`graph_ppr.personalized_pagerank`) y luego la integración vía `retriever.graph_expand()`, con
el caso que motiva la pieza: un candidato SOLO alcanzable en 2 saltos, invisible al 1-hop, visible al PPR.
Sin red (embeddings hash). Ejecutar: .venv/bin/pytest tests/memory/unit/test_graph_ppr.py
"""
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import graph_ppr as ppr
from memory import retriever
from memory import writer


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


# ── módulo puro ────────────────────────────────────────────────────────────────────────────────────────────

def test_empty_seed_returns_empty(fresh_db):
    assert ppr.personalized_pagerank({}) == {}


def test_isolated_node_never_proposes_a_neighbor(fresh_db):
    a = writer.insert_memory("nodo aislado, sin aristas")
    ranks = ppr.personalized_pagerank({a: 1.0})
    # sin aristas no hay nada que proponer MÁS ALLÁ del propio sembrado — `_ppr_expand` lo filtra igualmente
    # (un candidato nunca puede ser una de sus propias semillas), pero el módulo puro no debe inventar vecinos.
    assert set(ranks) <= {a}


def test_two_hop_neighbor_gets_positive_mass(fresh_db):
    a = writer.insert_memory("a")
    b = writer.insert_memory("b")
    c = writer.insert_memory("c")   # solo alcanzable DESDE a vía b (2 saltos)
    writer.link(a, b, "about", 1.0)
    writer.link(b, c, "about", 1.0)
    ranks = ppr.personalized_pagerank({a: 1.0})
    assert c in ranks and ranks[c] > 0
    # el vecino directo (1 salto) debe acumular más masa que el de 2 saltos.
    assert ranks[b] > ranks[c]


def test_unreachable_node_is_absent(fresh_db):
    a = writer.insert_memory("a")
    b = writer.insert_memory("b")
    isolated = writer.insert_memory("isolated")   # sin ninguna arista hacia/desde a
    writer.link(a, b, "about", 1.0)
    ranks = ppr.personalized_pagerank({a: 1.0})
    assert isolated not in ranks


def test_broken_db_fails_open(fresh_db, monkeypatch):
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(memdb, "get_db", _boom)
    assert ppr.personalized_pagerank({1: 1.0}) == {}


# ── integración con retriever.graph_expand() ──────────────────────────────────────────────────────────────

def _pill(text: str) -> dict:
    """Fila mínima con la forma que espera `graph_expand()` como `results` de entrada."""
    mid = writer.insert_memory(text, level="long", kind="fact")
    db = memdb.get_db()
    row = db.query_one(
        "SELECT id, level, kind, text, importance, weight, last_access, pinned FROM memories WHERE id=?",
        (mid,),
    )
    m = dict(row)
    m["score"] = 1.0
    return m


def test_graph_expand_finds_two_hop_candidate_one_hop_misses(fresh_db):
    seed = _pill("bicicleta Trek de carretera")
    mid = _pill("reparar la rueda trasera")
    target = _pill("carrera ciclista en tres semanas")   # solo a 2 saltos del seed
    writer.link(seed["id"], mid["id"], "about", 1.0)
    writer.link(mid["id"], target["id"], "about", 1.0)

    expanded = retriever.graph_expand([seed], top=6, max_add=0, ppr_max_add=6)
    ids = {r["id"] for r in expanded}
    assert target["id"] in ids
    added = [r for r in expanded if r["id"] == target["id"]][0]
    assert added["via"] == "ppr"


def test_ppr_never_duplicates_what_one_hop_already_added(fresh_db):
    seed = _pill("bicicleta Trek de carretera")
    direct = _pill("reparar la rueda trasera")
    writer.link(seed["id"], direct["id"], "about", 1.0)

    expanded = retriever.graph_expand([seed], top=6, max_add=8, ppr_max_add=6)
    ids = [r["id"] for r in expanded]
    assert ids.count(direct["id"]) == 1   # el 1-hop ya lo trajo; PPR no lo repite


def test_kill_switch_disables_ppr_channel(fresh_db, monkeypatch):
    monkeypatch.setenv("ZAELAR_GRAPH_PPR", "0")
    seed = _pill("bicicleta Trek de carretera")
    mid = _pill("reparar la rueda trasera")
    target = _pill("carrera ciclista en tres semanas")
    writer.link(seed["id"], mid["id"], "about", 1.0)
    writer.link(mid["id"], target["id"], "about", 1.0)

    expanded = retriever.graph_expand([seed], top=6, max_add=0, ppr_max_add=6)
    ids = {r["id"] for r in expanded}
    assert target["id"] not in ids   # sin el canal PPR, el 2-hop sigue invisible (comportamiento pre-pieza)


def test_graph_expand_with_no_edges_at_all_is_unaffected(fresh_db):
    seed = _pill("nodo sin ninguna arista")
    expanded = retriever.graph_expand([seed])
    assert expanded == [seed]
