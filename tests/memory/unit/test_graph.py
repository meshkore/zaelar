"""Tests de memory/graph.py (V2-002 · T50) — link + neighbors + expand (BFS acotado)."""
import pytest

from memory import db as memdb
from memory import embeddings as mememb
from memory import graph as memgraph
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


def test_link_and_neighbors(fresh_db):
    a = memwriter.insert_memory("a")
    b = memwriter.insert_memory("b")
    c = memwriter.insert_memory("c")
    memgraph.link(a, b, "about", 0.5)
    memgraph.link(a, c, "about", 0.9)
    ns = memgraph.neighbors(a)
    assert [n["to_id"] for n in ns] == [c, b]  # ordenado por peso desc


def test_neighbors_filter_by_type(fresh_db):
    a = memwriter.insert_memory("a")
    b = memwriter.insert_memory("b")
    c = memwriter.insert_memory("c")
    memgraph.link(a, b, "about", 1.0)
    memgraph.link(a, c, "caused", 1.0)
    ns = memgraph.neighbors(a, type="caused")
    assert [n["to_id"] for n in ns] == [c]


def test_expand_depth_one(fresh_db):
    a = memwriter.insert_memory("a")
    b = memwriter.insert_memory("b")
    memgraph.link(a, b, "about", 1.0)
    reached = memgraph.expand([a], depth=1)
    assert reached == {b}


def test_expand_depth_two(fresh_db):
    a = memwriter.insert_memory("a")
    b = memwriter.insert_memory("b")
    c = memwriter.insert_memory("c")
    memgraph.link(a, b, "about", 1.0)
    memgraph.link(b, c, "about", 1.0)
    assert memgraph.expand([a], depth=1) == {b}
    assert memgraph.expand([a], depth=2) == {b, c}


def test_expand_excludes_start_and_handles_cycles(fresh_db):
    a = memwriter.insert_memory("a")
    b = memwriter.insert_memory("b")
    memgraph.link(a, b, "about", 1.0)
    memgraph.link(b, a, "about", 1.0)  # ciclo
    reached = memgraph.expand([a], depth=3)
    assert a not in reached and reached == {b}
