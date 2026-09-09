"""The canonical communications archive (V2-628 F0): the one copy that does not expire.

Before it, every message body was written twice (thread store, msg pill) and both copies expire by design —
a question about a message from a month ago was unanswerable from any store we control. These tests pin the
F0 contract: every write seam lands in the archive, the archive is idempotent under retries and re-fetches,
and a row is still findable when every expiring view has already dropped it.
"""
import time

import pytest

from connectors.messaging import archive
from connectors.messaging import store as msgstore
from memory import db as memdb
from memory import embeddings as mememb


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture(autouse=True)
def fresh_memory(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    yield
    memdb.reset_db()


@pytest.fixture(autouse=True)
def isolated_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(archive, "_db_path", lambda: str(tmp_path / "archive.db"))
    archive.reset()
    yield
    archive.reset()


@pytest.fixture
def isolated_widget_store(monkeypatch):
    state = {"db": msgstore._empty()}
    monkeypatch.setattr(msgstore, "load", lambda: state["db"])
    monkeypatch.setattr(msgstore, "save", lambda db: state.update(db=db) or db)
    yield state


def test_an_inbound_message_outlives_every_expiring_view(isolated_widget_store):
    msgstore.upsert_items("whatsapp", [{
        "messageId": "m1", "chatId": "g9", "senderName": "Marta", "chatName": "Cole 5ºB",
        "isGroup": True, "body": "reunión del comedor el jueves", "urgencia": "media",
        "dirigido_a_mi": False, "ts": time.time(),
    }])
    # Simulate every view expiring: the UI store is wiped entirely.
    isolated_widget_store["db"] = msgstore._empty()
    rows = archive.search(sender="Marta")
    assert rows and rows[0]["body"] == "reunión del comedor el jueves"
    assert rows[0]["direction"] == "in" and rows[0]["platform"] == "whatsapp"


def test_the_same_message_twice_is_one_row():
    msg = {"messageId": "m7", "body": "hola", "ts": 1000.0, "from": "Ana"}
    assert archive.record("telegram", "c1", [msg]) == 1
    assert archive.record("telegram", "c1", [msg]) == 0
    assert archive.stats()["messages"] == 1


def test_an_outbound_reply_lands_and_answers_replied(isolated_widget_store):
    t0 = time.time()
    msgstore.record_outbound("whatsapp", "g9", {"messageId": "o1", "body": "voy yo al comedor",
                                                "ts": t0 + 5}, name="Cole 5ºB")
    row = archive.replied("whatsapp", "g9", after_ts=t0)
    assert row is not None and row["direction"] == "out" and row["body"] == "voy yo al comedor"
    assert archive.replied("whatsapp", "g9", after_ts=t0 + 10) is None


def test_a_history_landing_is_archived_with_its_chat_label(isolated_widget_store):
    msgs = [{"id": "h1", "who": "Luis", "body": "¿reservamos el hotel?", "ts": 500.0, "dir": "in"},
            {"id": "h2", "who": "yo", "body": "reservo yo mañana", "ts": 600.0, "dir": "out"}]
    msgstore.add_history("telegram", "trip", msgs, name="Viaje Semana Santa", is_group=True)
    rows = archive.search(chat="Viaje")
    assert {r["msg_id"] for r in rows} == {"h1", "h2"}
    assert all(r["chat_name"] == "Viaje Semana Santa" and r["is_group"] == 1 for r in rows)
    assert {r["direction"] for r in rows} == {"in", "out"}
    # A re-fetch of the same window (the 60s-cache / load_more overlap case) inserts nothing twice.
    msgstore.add_history("telegram", "trip", msgs, name="Viaje Semana Santa", is_group=True)
    assert archive.stats()["messages"] == 2


def test_search_walks_text_and_filters():
    now = time.time()
    archive.record("email", "school", [
        {"messageId": "e1", "from": "CRA EL VALLE", "body": "menú del comedor de octubre", "ts": now - 40 * 86400},
        {"messageId": "e2", "from": "CRA EL VALLE", "body": "excursión al museo", "ts": now - 3 * 86400},
        {"messageId": "e3", "from": "Banco", "body": "su recibo", "ts": now - 2 * 86400},
    ], direction="in", chat_name="CRA EL VALLE")
    assert [r["msg_id"] for r in archive.search(q="comedor")] == ["e1"]
    last_month = archive.search(sender="valle", since=now - 30 * 86400)
    assert [r["msg_id"] for r in last_month] == ["e2"], "sender is case-insensitive and `since` bounds the window"
    assert len(archive.search(platform="email")) == 3


def test_a_broken_archive_never_breaks_the_store(isolated_widget_store, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(archive, "record_items", boom)
    monkeypatch.setattr(archive, "record", boom)
    out = msgstore.upsert_items("telegram", [{"messageId": "x1", "chatId": "c", "senderName": "Eva",
                                              "body": "sigo entrando", "urgencia": "baja"}])
    assert any(it.get("messageId") == "x1" for it in out.get("items", []))
