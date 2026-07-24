"""Test de volcado a memoria de los mensajes entrantes (V2-003 · T57)."""
import pytest

from connectors.messaging import store as msgstore
from memory import db as memdb
from memory import embeddings as mememb
from memory import retriever as memret


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


@pytest.fixture
def isolated_widget_store(monkeypatch):
    """Aísla el store de UI del widget (widgets/_data) para no tocar el disco real."""
    state = {"db": msgstore._empty()}
    monkeypatch.setattr(msgstore, "load", lambda: state["db"])
    monkeypatch.setattr(msgstore, "save", lambda db: state.update(db=db) or db)
    yield state


def test_incoming_message_becomes_searchable_memory(fresh_db, isolated_widget_store):
    msgstore.upsert_items("telegram", [{
        "messageId": "m1", "chatId": "c1", "senderName": "Marta",
        "body": "¿nos vemos mañana para lo del alquiler?", "urgencia": "alta",
        "dirigido_a_mi": True,
    }])
    # el mensaje entró al store de UI...
    assert any(it["body"].startswith("¿nos vemos") for it in isolated_widget_store["db"]["items"])
    # ...y ADEMÁS es un recuerdo `msg` recuperable
    res = memret.search("alquiler", limit=5, expand=False)
    assert res, "el mensaje entrante debe ser buscable en la memoria"
    row = memdb.get_db().query_one("SELECT kind FROM memories WHERE text LIKE '%alquiler%'")
    assert row is not None and row["kind"] == "msg"


def test_duplicate_not_dumped_twice(fresh_db, isolated_widget_store):
    item = {"messageId": "dup", "chatId": "c", "senderName": "X", "body": "hola qué tal", "urgencia": "media"}
    msgstore.upsert_items("whatsapp", [item])
    msgstore.upsert_items("whatsapp", [item])   # mismo messageId → dedupe en el store
    rows = memdb.get_db().query("SELECT id FROM memories WHERE text LIKE '%hola qué tal%'")
    assert len(rows) == 1


def test_empty_body_not_dumped(fresh_db, isolated_widget_store):
    msgstore.upsert_items("telegram", [{"messageId": "e1", "chatId": "c", "body": "", "urgencia": "baja"}])
    rows = memdb.get_db().query("SELECT id FROM memories WHERE kind='msg'")
    assert rows == []
