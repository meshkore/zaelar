#
# test_owner_v2.py — el owner backed del widget mensajería (V2-008). Verifica el reshape v2 END-TO-END en la
# frontera del bus (sin red, con triaje stub): un connector.msg entrante RELEVANTE se tría, aflora al store de UI
# y (por el mismo upsert) a la memoria; uno irrelevante NO aflora; connector.status se refleja en la tarjeta; y
# una acción "read" publica msg.mark_read al bus (para que el conector correcto marque leído en su app).
# Ejecutar: .venv/bin/python -m pytest widgets/mensajeria/test_owner_v2.py
#
import asyncio

import pytest

import bus
from connectors.messaging import ingest, notify
from connectors.messaging import store as msgstore
from widgets import store as wstore
from widgets.mensajeria import data, owner as owner_mod, triage_agent


@pytest.fixture
def iso(monkeypatch, tmp_path):
    """Aísla el store del widget (widgets/_data → tmp), silencia el volcado a memoria y el aviso hablado, y
    limpia el bus. Deja intacta la lógica real de triage_batch/handle/apply_action."""
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    wstore._last_hash.clear()
    monkeypatch.setattr(msgstore, "_to_memory", lambda items: None)

    async def _noop_announce(label, items):
        return None
    monkeypatch.setattr(notify, "announce", _noop_announce)
    bus.reset()
    yield
    bus.reset()


def _mk_owner():
    o = owner_mod._Owner()
    o._msg_sub = bus.subscribe(ingest.TOPIC_MSG)
    o._status_sub = bus.subscribe(ingest.TOPIC_STATUS)
    return o


def test_relevant_incoming_surfaces_to_store(iso, monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": True, "dirigido_a_mi": True, "urgencia": "alta", "motivo": "te escribe"}
                for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)

    async def run():
        o = _mk_owner()
        ingest.publish_msg("telegram", {"messageId": "m1", "chatId": "c1", "senderId": "s1",
                                        "senderName": "Marta", "isGroup": False, "body": "¿nos vemos hoy?"})
        await o._triage_batch()

    asyncio.run(run())
    v = data.view_data()
    assert v["count"] == 1
    assert v["items"][0]["from"] == "Marta"
    assert v["items"][0]["platform"] == "telegram"


def test_irrelevant_incoming_does_not_surface(iso, monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": False, "dirigido_a_mi": False, "urgencia": "baja", "motivo": "spam"}
                for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)

    async def run():
        o = _mk_owner()
        ingest.publish_msg("whatsapp", {"messageId": "x1", "chatId": "g1", "isGroup": True,
                                        "chatName": "Ofertas", "senderName": "bot", "body": "🔥 -70%"})
        await o._triage_batch()

    asyncio.run(run())
    assert data.view_data()["count"] == 0


def test_status_event_reflected_in_card(iso):
    async def run():
        o = _mk_owner()
        ingest.publish_status("telegram", "connecting", qr="data:image/png;base64,ZZZ")
        o._apply_status()

    asyncio.run(run())
    plat = data.view_data()["platforms"]["telegram"]
    assert plat["status"] == "connecting" and plat["qr"] == "data:image/png;base64,ZZZ"


def test_read_action_publishes_mark_read(iso, monkeypatch):
    async def fake_classify(msgs, name=None):
        return [{**m, "importante": True, "dirigido_a_mi": True, "urgencia": "alta", "motivo": "x"} for m in msgs]
    monkeypatch.setattr(triage_agent, "classify", fake_classify)

    marks = bus.subscribe(ingest.TOPIC_MARK_READ)

    async def run():
        o = _mk_owner()
        ingest.publish_msg("telegram", {"messageId": "m1", "chatId": "c1", "senderId": "s1",
                                        "senderName": "Ana", "isGroup": False, "body": "hola"})
        await o._triage_batch()
        assert data.view_data()["count"] == 1
        await o.handle("read", {"n": 1})

    asyncio.run(run())
    # el item se fue del widget...
    assert data.view_data()["count"] == 0
    # ...y su clave salió al bus para que Telegram lo marque leído.
    key = marks.queue.get_nowait()
    assert key["platform"] == "telegram" and key["messageId"] == "m1"
