"""Test del flujo de RESPONDER (V2-051): apply_action('reply') → pending_reply → drenaje → bus msg.reply.

Genérico por canal; se ejercita con un item de email (el único conector con envío hoy)."""
import pytest

from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import data as mdata


@pytest.fixture
def isolated_store(monkeypatch):
    """Aísla el fichero de estado del widget (mismo id, mismo backend) para no tocar el disco real."""
    state = {}

    def _load(wid, default=None):
        return state.get(wid, default if default is not None else {})

    def _save(wid, db):
        state[wid] = db
        return db
    monkeypatch.setattr(wstore, "load", _load)
    monkeypatch.setattr(wstore, "save", _save)
    yield state


def _seed_email_item(**over):
    it = {"platform": "email", "messageId": "99", "chatId": "pablo@example.com",
          "senderId": "pablo@example.com", "from": "Pablo", "group": None, "isGroup": False,
          "body": "[Asunto: Cena] ¿Vienes?", "urgencia": "alta", "dirigido_a_mi": True, "motivo": "",
          "subject": "Cena", "msgid": "<abc@ex>"}
    it.update(over)
    return it


def test_reply_enqueues_pending_reply_with_threading(isolated_store, monkeypatch):
    # un chat de email en el store (sin volcado a memoria: lo cortocircuitamos)
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    msgstore.upsert_items("email", [_seed_email_item()])

    # el operador responde al CHAT nº1 (lista de chats, sin chat abierto)
    mdata.apply_action("reply", {"n": 1, "text": "Sí, allí estaré"})

    pending = msgstore.take_pending_reply("email")
    assert len(pending) == 1
    r = pending[0]
    assert r["platform"] == "email"
    assert r["to"] == "pablo@example.com"
    assert r["subject"] == "Cena"
    assert r["msgid"] == "<abc@ex>"           # threading correcto
    assert r["text"] == "Sí, allí estaré"
    assert r["messageId"] == "99"             # UID para marcar leído tras enviar


def test_reply_also_marks_read_and_removes_item(isolated_store, monkeypatch):
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    msgstore.upsert_items("email", [_seed_email_item()])
    mdata.apply_action("reply", {"n": 1, "text": "vale"})
    # el item respondido se quita de la lista y se encola su mark-read
    assert not mdata.view_data()["items"]
    reads = msgstore.take_pending_read("email")
    assert any(k["messageId"] == "99" for k in reads)


def test_reply_ignored_without_text(isolated_store, monkeypatch):
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)
    msgstore.upsert_items("email", [_seed_email_item()])
    mdata.apply_action("reply", {"n": 1, "text": "   "})
    assert not msgstore.take_pending_reply()   # nada encolado


def test_reply_inbox_filters_by_platform():
    """ReplyInbox('email') solo consume msg.reply de email; descarta los de otras plataformas."""
    from connectors.messaging import ingest
    inbox = ingest.ReplyInbox("email")
    try:
        ingest.publish_reply({"platform": "email", "to": "a@x.com", "text": "hi"})
        ingest.publish_reply({"platform": "telegram", "to": "123", "text": "no"})
        got = inbox.drain()
        assert len(got) == 1 and got[0]["platform"] == "email"
    finally:
        inbox.close()
