"""V2-624 — the two gaps the operator hit live (sid 952fcf2f, 2026-09-08): «todas las conversaciones que
hayan tenido actividad en las últimas 72 horas» had no criterion anywhere, and «¿puedes ir al conector y
chupar más mensajes?» had no door. Both were refused honestly; this file pins the mechanisms that close them.

The criterion is per-platform STATE (his words): setting it persists until changed, a plain `show_view`
keeps it, `window_h: 0` clears it. The fetch is a queue→bus round trip like `load_more`; WhatsApp's refusal
is part of the contract — its transport has no bulk door, and offering one that cannot work is worse.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import data


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    yield


def _seed_threads(now=None):
    now = now or time.time()
    db = data.load_db()
    db["threads"] = {
        "whatsapp|111": {"name": "Jose Vicente", "complete": False, "touched": now, "msgs": [
            {"id": "a1", "dir": "in", "who": "Jose Vicente", "body": "hola", "ts": now - 3600, "read": True},
            {"id": "a2", "dir": "out", "who": "Tú", "body": "qué tal", "ts": now - 1800, "read": True}]},
        "whatsapp|222": {"name": "Viejo", "complete": False, "touched": now - 90 * 3600, "msgs": [
            {"id": "b1", "dir": "in", "who": "Viejo", "body": "antiguo", "ts": now - 90 * 3600, "read": True}]},
        "whatsapp|333": {"name": "Grupo Viaje", "isGroup": True, "complete": False, "touched": now, "msgs": [
            {"id": "c1", "dir": "in", "who": "Ana", "body": "vuelos el 12", "ts": now - 7200, "read": False},
            {"id": "c2", "dir": "in", "who": "Luis", "body": "del 12 al 19", "ts": now - 7000, "read": False}]},
        "telegram|444": {"name": "Marta", "complete": False, "touched": now, "msgs": [
            {"id": "d1", "dir": "in", "who": "Marta", "body": "reunión", "ts": now - 600, "read": False}]},
    }
    wstore.save("mensajeria", db)
    return now


def test_window_h_sets_the_criterion_and_answers_with_activity():
    _seed_threads()
    r = data.apply_action("show_view", {"platform": "whatsapp", "window_h": 72})
    res = r["result"]
    assert res["criteria"] == {"window_h": 72.0}
    names = [a["name"] for a in res["activity"]]
    # Newest last-message first; the 90-hour-old conversation is outside the window; Telegram's thread never
    # leaks into WhatsApp's lens.
    assert names == ["Jose Vicente", "Grupo Viaje"], names
    group_row = next(a for a in res["activity"] if a["name"] == "Grupo Viaje")
    assert group_row["isGroup"] is True and group_row["unread"] == 2


def test_a_plain_show_view_keeps_the_criterion_and_zero_clears_it():
    _seed_threads()
    data.apply_action("show_view", {"platform": "whatsapp", "window_h": 72})
    r = data.apply_action("show_view", {"platform": "whatsapp"})
    assert r["result"].get("criteria") == {"window_h": 72.0}, "the criterion is state, not per-utterance"
    v = data.view_data()
    assert v["lens_criteria"] == {"whatsapp": {"window_h": 72.0}}
    assert {c["name"] for c in v["activity_chats"]} == {"Jose Vicente", "Grupo Viaje"}
    data.apply_action("show_view", {"platform": "whatsapp", "window_h": 0})
    v = data.view_data()
    assert v["lens_criteria"] == {} and v["activity_chats"] == []


def test_activity_movement_includes_what_he_read_and_what_he_sent():
    """«Movimiento» is the thread store's view, not the pending inbox's: Jose Vicente's chat has NOTHING
    unread (his own reply closed it) and still shows, because the conversation moved."""
    _seed_threads()
    r = data.apply_action("show_view", {"platform": "whatsapp", "window_h": 72})
    jv = next(a for a in r["result"]["activity"] if a["name"] == "Jose Vicente")
    assert jv["unread"] == 0


def test_fetch_now_queues_for_telegram_and_the_owner_flushes_it_to_the_bus(monkeypatch):
    _seed_threads()
    from connectors.messaging import ingest
    from widgets.mensajeria import owner
    sent = []
    monkeypatch.setattr(ingest, "publish_fetch", lambda o: sent.append(dict(o)))
    asyncio.run(owner.handle("fetch_now", {"platform": "telegram", "since_hours": 24}))
    assert sent == [{"platform": "telegram", "since_hours": 24.0}]
    assert data.load_db()["pending_fetch"] == [], "the flush must drain the queue"


def test_whatsapp_fetch_is_refused_naming_what_is_possible():
    r = data.answer_action("fetch_now", {"platform": "whatsapp"})
    assert r["ok"] is False
    assert "tiempo real" in r["error"] and "load_more" in r["error"]
    # And the apply path refuses too — the veto cannot depend on which route the order took.
    r2 = data.apply_action("fetch_now", {"platform": "whatsapp"})
    assert r2["ok"] is False


def test_open_by_identity_only_opens_what_we_hold():
    _seed_threads()
    data.apply_action("open", {"platform": "whatsapp", "chatId": "333"})
    assert data.load_db()["active_chat"] == {"platform": "whatsapp", "chatId": "333"}
    r = data.apply_action("open", {"platform": "whatsapp", "chatId": "999"})
    assert r.get("ok") is False, "an identity we do not hold would paint an empty thread"


def test_a_reset_preserves_the_operator_configuration():
    """`blank()` (the operator's Reset) wipes messages and queues — never the autoresponder he set for his
    vacation nor his view criteria: a reset that silently stops answering in his name is the worse surprise."""
    from widgets.mensajeria import autorespond
    _seed_threads()
    db = data.load_db()
    autorespond.set_config(db, "whatsapp", text="De vacaciones")
    db["lens_criteria"] = {"telegram": {"window_h": 48.0}}
    wstore.save("mensajeria", db)
    fresh = data.blank()
    assert fresh["autoresponder"]["whatsapp"]["text"] == "De vacaciones"
    assert fresh["lens_criteria"] == {"telegram": {"window_h": 48.0}}
    assert fresh["items"] == [] and fresh["threads"] == {}
