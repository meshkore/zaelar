#
# test_ingest.py — la capa STATELESS de mensajería v2 (V2-008). Verifica: el gate v2 (sigue al cerebro nucleo,
# con override por env), la publicación de connector.msg / connector.status / msg.mark_read al bus, y que la
# MarkReadInbox de un conector solo drena las órdenes de SU plataforma.
# Ejecutar: .venv/bin/python -m pytest connectors/messaging/test_ingest.py
#
import pytest

import bus
from connectors.messaging import ingest


@pytest.fixture(autouse=True)
def _clean_bus():
    bus.reset()
    yield
    bus.reset()


def test_v2_gate_follows_env_override(monkeypatch):
    monkeypatch.setenv("ZAELAR_MSG_V2", "1")
    assert ingest.v2_enabled() is True
    monkeypatch.setenv("ZAELAR_MSG_V2", "0")
    assert ingest.v2_enabled() is False


def test_v2_gate_follows_brain_when_no_override(monkeypatch):
    monkeypatch.delenv("ZAELAR_MSG_V2", raising=False)
    monkeypatch.setattr("config.v2.active_brain", lambda: "nucleo")
    assert ingest.v2_enabled() is True
    monkeypatch.setattr("config.v2.active_brain", lambda: "direct")
    assert ingest.v2_enabled() is False


def test_publish_msg_reaches_subscriber():
    sub = bus.subscribe(ingest.TOPIC_MSG)
    ingest.publish_msg("telegram", {"messageId": "m1", "body": "hola"})
    ev = sub.queue.get_nowait()
    assert ev["platform"] == "telegram"
    assert ev["messageId"] == "m1" and ev["body"] == "hola"


def test_publish_status_reaches_subscriber():
    sub = bus.subscribe(ingest.TOPIC_STATUS)
    ingest.publish_status("whatsapp", "connecting", qr="data:image/png;base64,AAAA")
    ev = sub.queue.get_nowait()
    assert ev == {"platform": "whatsapp", "status": "connecting", "qr": "data:image/png;base64,AAAA",
                  "detail": None}


def test_mark_read_inbox_filters_by_platform():
    wa = ingest.MarkReadInbox("whatsapp")
    tg = ingest.MarkReadInbox("telegram")
    ingest.publish_mark_read({"platform": "whatsapp", "chatId": "c1", "messageId": "wa1"})
    ingest.publish_mark_read({"platform": "telegram", "chatId": "c2", "messageId": "tg1"})
    wa_keys = wa.drain()
    tg_keys = tg.drain()
    assert [k["messageId"] for k in wa_keys] == ["wa1"]
    assert [k["messageId"] for k in tg_keys] == ["tg1"]
    # drenado consume: un segundo drain no repite.
    assert wa.drain() == []
    wa.close()
    tg.close()
