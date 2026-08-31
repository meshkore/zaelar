"""tests/memory/unit/test_graph_ppr.py — Personalized PageRank over `edges` (V2-111 §9.1).

By design, `graph_expand()` (1-hop) does not reach a 2-hop connection; these tests first exercise the
standalone module (`graph_ppr.personalized_pagerank`) and then the integration through
`retriever.graph_expand()`, with the case that motivates the feature: a candidate reachable ONLY in 2 hops,
invisible to 1-hop, visible to PPR. No network (hash embeddings). Run:
`.venv/bin/pytest tests/memory/unit/test_graph_ppr.py`
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


# ── standalone module ──────────────────────────────────────────────────────────────────────────────────────

def test_empty_seed_returns_empty(fresh_db):
    assert ppr.personalized_pagerank({}) == {}


def test_isolated_node_never_proposes_a_neighbor(fresh_db):
    a = writer.insert_memory("nodo aislado, sin aristas")
    ranks = ppr.personalized_pagerank({a: 1.0})
    # With no edges there is nothing to propose BEYOND the seed itself — `_ppr_expand` filters it out anyway
    # (a candidate can never be one of its own seeds), but the standalone module must not invent neighbors.
    assert set(ranks) <= {a}


def test_two_hop_neighbor_gets_positive_mass(fresh_db):
    a = writer.insert_memory("a")
    b = writer.insert_memory("b")
    c = writer.insert_memory("c")   # reachable ONLY FROM a through b (2 hops)
    writer.link(a, b, "about", 1.0)
    writer.link(b, c, "about", 1.0)
    ranks = ppr.personalized_pagerank({a: 1.0})
    assert c in ranks and ranks[c] > 0
    # The direct neighbor (1 hop) should accumulate more mass than the 2-hop neighbor.
    assert ranks[b] > ranks[c]


def test_unreachable_node_is_absent(fresh_db):
    a = writer.insert_memory("a")
    b = writer.insert_memory("b")
    isolated = writer.insert_memory("isolated")   # with no edge to/from a
    writer.link(a, b, "about", 1.0)
    ranks = ppr.personalized_pagerank({a: 1.0})
    assert isolated not in ranks


def test_broken_db_fails_open(fresh_db, monkeypatch):
    def _boom():
        raise RuntimeError("db down")
    monkeypatch.setattr(memdb, "get_db", _boom)
    assert ppr.personalized_pagerank({1: 1.0}) == {}


# ── integration with retriever.graph_expand() ───────────────────────────────────────────────────────────────

def _pill(text: str) -> dict:
    """Minimal row in the form that `graph_expand()` expects as input `results`."""
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
    target = _pill("carrera ciclista en tres semanas")   # only 2 hops from the seed
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
    assert ids.count(direct["id"]) == 1   # 1-hop already added it; PPR does not repeat it


def test_kill_switch_disables_ppr_channel(fresh_db, monkeypatch):
    monkeypatch.setenv("ZAELAR_GRAPH_PPR", "0")
    seed = _pill("bicicleta Trek de carretera")
    mid = _pill("reparar la rueda trasera")
    target = _pill("carrera ciclista en tres semanas")
    writer.link(seed["id"], mid["id"], "about", 1.0)
    writer.link(mid["id"], target["id"], "about", 1.0)

    expanded = retriever.graph_expand([seed], top=6, max_add=0, ppr_max_add=6)
    ids = {r["id"] for r in expanded}
    assert target["id"] not in ids   # without the PPR channel, 2-hop remains invisible (pre-feature behavior)


def test_graph_expand_with_no_edges_at_all_is_unaffected(fresh_db):
    seed = _pill("nodo sin ninguna arista")
    expanded = retriever.graph_expand([seed])
    assert expanded == [seed]
