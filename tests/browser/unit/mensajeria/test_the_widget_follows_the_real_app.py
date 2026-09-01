"""V2-546 — the messaging widget FOLLOWS the real apps instead of drifting from them.

Reported live: the operator answered two WhatsApp messages from his own phone, came back to the widget, and
they were still sitting there looking pending. Two structural facts behind it, both measured before touching
anything:

  · Every connector was wired INBOUND-ONLY. The WhatsApp bridge saw his outgoing messages (Baileys delivers
    them as upserts with fromMe:true) and dropped them with an explicit `continue`; Telethon subscribed to
    `NewMessage(incoming=True)` only; email polled INBOX and never looked at flags. Read state travelled one
    way, widget → app, and never back.
  · There was NO conversation store. `items` was the pending inbox and reading a message DELETED it, so
    opening a chat showed what was unread and nothing else — no history, and no way to continue a thread.

This file covers the seam that fixes both: the thread (widgets/mensajeria/thread.py), the store writers that
reflect what happened elsewhere, and the read side the widget paints.
"""
from __future__ import annotations

import json
import pathlib
import time

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
CHAT = "34600@s.whatsapp.net"


@pytest.fixture
def msg(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real inbox."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from connectors.messaging import store as ms
    from widgets.mensajeria import data as d
    return d, ms


def _inbound(ms, mid, body, ts, urgencia="media"):
    ms.upsert_items("whatsapp", [{
        "messageId": mid, "chatId": CHAT, "senderId": "34600", "from": "Francisco",
        "body": body, "urgencia": urgencia, "timestamp": ts}])


# ── The reported incident, end to end ───────────────────────────────────────
def test_answering_from_his_own_phone_clears_the_chat_here(msg):
    """THE case. He replies in WhatsApp; the widget stops showing that chat as pending."""
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "¿Quedamos mañana?", now - 300)
    _inbound(ms, "m2", "¿A las 5?", now - 200)
    assert len(ms.load()["items"]) == 2

    ms.record_outbound("whatsapp", CHAT, {"messageId": "m3", "body": "Sí, a las 5", "timestamp": now - 100})

    assert ms.load()["items"] == [], "answering elsewhere IS having dealt with it"
    assert d.view_data()["chats"] == []


def test_his_own_message_joins_the_conversation(msg):
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "¿Quedamos?", now - 300)
    ms.record_outbound("whatsapp", CHAT, {"messageId": "m3", "body": "Sí", "timestamp": now - 100})
    d.apply_action("open", {"name": "Francisco"})

    thread = d.view_data()["active_items"]
    assert [(m["body"], m["dir"]) for m in thread] == [("¿Quedamos?", "in"), ("Sí", "out")]


def test_a_message_arriving_AFTER_his_reply_is_not_swallowed(msg):
    """The watermark is what keeps this honest: clearing a chat must not hide what came later."""
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "¿Quedamos?", now - 300)
    ms.record_outbound("whatsapp", CHAT, {"messageId": "m3", "body": "Sí", "timestamp": now - 200})
    _inbound(ms, "m4", "Perfecto, nos vemos", now - 10)

    items = ms.load()["items"]
    assert [it["messageId"] for it in items] == ["m4"]


def test_reading_it_elsewhere_only_clears_up_to_the_watermark(msg):
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "uno", now - 300)
    _inbound(ms, "m2", "dos", now - 100)

    ms.apply_external_read("whatsapp", CHAT, upto_ts=now - 200)

    assert [it["messageId"] for it in ms.load()["items"]] == ["m2"]


def test_reading_elsewhere_never_orders_the_app_to_mark_read(msg):
    """The app is the one that just told US. Echoing it back is a loop, and mark-read is not free."""
    d, ms = msg
    _inbound(ms, "m1", "uno", time.time() - 100)
    ms.apply_external_read("whatsapp", CHAT)
    assert ms.load()["pending_read"] == []


def test_email_can_be_exact_about_WHICH_mail_was_read(msg):
    """IMAP answers per message (\\Seen / \\Answered), not with a watermark — so the ids path exists."""
    d, ms = msg
    now = time.time()
    ms.upsert_items("email", [
        {"messageId": "10", "chatId": "a@b.com", "from": "A", "body": "uno", "timestamp": now - 200},
        {"messageId": "11", "chatId": "a@b.com", "from": "A", "body": "dos", "timestamp": now - 100}])

    ms.apply_external_read("email", "a@b.com", ids=["10"])

    assert [it["messageId"] for it in ms.load()["items"]] == ["11"]


# ── The conversation survives being read ────────────────────────────────────
def test_reading_a_message_here_empties_the_inbox_and_KEEPS_the_thread(msg):
    """The whole point: the inbox is what still wants attention, the thread is what was said. Before this
    they were one list, so answering everything destroyed the conversation."""
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "uno", now - 300)
    _inbound(ms, "m2", "dos", now - 100)
    d.apply_action("open", {"name": "Francisco"})
    d.apply_action("read", {"n": 1})
    d.apply_action("read", {"n": 1})

    view = d.view_data()
    assert ms.load()["items"] == []
    assert [m["body"] for m in view["active_items"]] == ["uno", "dos"]
    assert view["active_chat"] is not None, "an emptied inbox must not throw him out of the conversation"


def test_a_read_message_offers_no_action_it_cannot_perform(msg):
    """Once out of the inbox a row has no `n`, which is what the ✓/✕ buttons address. widget.js hides them
    on exactly that condition — a button whose payload cannot resolve is a lie about what pressing it does."""
    d, ms = msg
    _inbound(ms, "m1", "uno", time.time() - 100)
    d.apply_action("open", {"name": "Francisco"})
    d.apply_action("read", {"n": 1})
    assert d.view_data()["active_items"][0].get("n") is None


def test_an_operators_own_message_is_never_actionable(msg):
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "uno", now - 300)
    ms.record_outbound("whatsapp", CHAT, {"messageId": "m3", "body": "mío", "timestamp": now - 100})
    d.apply_action("open", {"name": "Francisco"})
    mine = [m for m in d.view_data()["active_items"] if m["dir"] == "out"][0]
    assert mine.get("n") is None and mine["read"] is True


def test_a_chat_with_nothing_at_all_still_closes_itself(msg):
    """The auto-close is not deleted, only conditioned: with no pending item AND no history there is nothing
    to come back to, and leaving an empty thread open would be the old bug in reverse."""
    d, ms = msg
    _inbound(ms, "m1", "uno", time.time() - 100)
    d.apply_action("open", {"name": "Francisco"})
    db = d.load_db()
    db["threads"] = {}
    db["items"] = []
    from widgets import store
    store.save("mensajeria", db)
    assert d.view_data()["active_chat"] is None


def test_a_thread_that_predates_this_still_opens(msg):
    """An install upgrading into this has items and no threads. Falling back to the pending items is what
    keeps that operator's widget working on the first run after the update."""
    d, ms = msg
    _inbound(ms, "m1", "uno", time.time() - 100)
    db = d.load_db()
    db["threads"] = {}
    from widgets import store
    store.save("mensajeria", db)
    d.apply_action("open", {"name": "Francisco"})
    assert [m["body"] for m in d.view_data()["active_items"]] == ["uno"]


# ── "Load previous" ─────────────────────────────────────────────────────────
def test_load_more_is_declared_so_the_voice_can_ask_for_it(msg):
    manifest = json.loads((ENGINE / "widgets" / "mensajeria" / "manifest.json").read_text(encoding="utf-8"))
    assert "load_more" in manifest["actions"], "an undeclared capability is one the model narrates (V2-520)"


def test_load_more_enqueues_an_order_for_the_connector_and_invents_nothing(msg):
    d, ms = msg
    _inbound(ms, "m1", "uno", time.time() - 100)
    d.apply_action("open", {"name": "Francisco"})
    before = len(d.view_data()["active_items"])

    out = d.apply_action("load_more", {})

    assert out["ok"] is True
    order = ms.load()["pending_history"][0]
    assert order["platform"] == "whatsapp" and order["beforeId"] == "m1"
    assert len(d.view_data()["active_items"]) == before, "asking is not receiving"


def test_load_more_without_an_open_chat_says_how_to_fix_it(msg):
    d, ms = msg
    out = d.apply_action("load_more", {})
    assert out["ok"] is False and "open" in out["error"]


def test_older_messages_land_ABOVE_and_close_the_boundary(msg):
    d, ms = msg
    now = time.time()
    _inbound(ms, "m1", "reciente", now - 100)
    d.apply_action("open", {"name": "Francisco"})
    assert d.view_data()["thread_meta"]["can_load_more"] is True

    ms.add_history("whatsapp", CHAT, [
        {"messageId": "old1", "dir": "in", "from": "Francisco", "body": "antiguo", "ts": now - 90000}],
        complete=True)

    view = d.view_data()
    assert [m["body"] for m in view["active_items"]] == ["antiguo", "reciente"]
    assert view["thread_meta"]["complete"] is True
    assert view["thread_meta"]["can_load_more"] is False, "stop offering what has no answer left"


def test_the_boundary_is_not_offered_where_the_transport_cannot_serve_it(msg, monkeypatch):
    """`_HISTORY_PLATFORMS` is a statement about each transport, not a preference. Offering a button that
    cannot work is worse than not offering one."""
    d, ms = msg
    monkeypatch.setattr(d, "_HISTORY_PLATFORMS", ("telegram",))
    _inbound(ms, "m1", "uno", time.time() - 100)
    d.apply_action("open", {"name": "Francisco"})
    assert d.view_data()["thread_meta"]["can_load_more"] is False
    assert d.apply_action("load_more", {})["ok"] is False


# ── The thread module's own rules ───────────────────────────────────────────
def test_the_same_message_twice_does_not_duplicate_the_thread():
    from widgets.mensajeria import thread
    db = {}
    thread.append(db, "whatsapp", CHAT, {"messageId": "m1", "body": "uno", "ts": 1.0}, "in")
    thread.append(db, "whatsapp", CHAT, {"messageId": "m1", "body": "uno", "ts": 1.0}, "in")
    assert len(thread.window(db, "whatsapp", CHAT)) == 1


def test_a_redelivery_does_not_resurrect_an_unread_mark():
    from widgets.mensajeria import thread
    db = {}
    thread.append(db, "whatsapp", CHAT, {"messageId": "m1", "body": "uno", "ts": 1.0}, "in")
    thread.mark_read(db, "whatsapp", CHAT)
    thread.append(db, "whatsapp", CHAT, {"messageId": "m1", "body": "uno", "ts": 1.0}, "in")
    assert thread.window(db, "whatsapp", CHAT)[0]["read"] is True


def test_a_late_outgoing_message_lands_in_TIME_order_not_arrival_order():
    """An "out" captured from the phone can reach us after a later inbound one; a thread out of order reads
    as a different conversation."""
    from widgets.mensajeria import thread
    db = {}
    thread.append(db, "whatsapp", CHAT, {"messageId": "b", "body": "después", "ts": 200.0}, "in")
    thread.append(db, "whatsapp", CHAT, {"messageId": "a", "body": "antes", "ts": 100.0}, "out")
    assert [m["body"] for m in thread.window(db, "whatsapp", CHAT)] == ["antes", "después"]


def test_dropping_the_oldest_message_stops_claiming_the_thread_is_complete():
    from widgets.mensajeria import thread
    db = {}
    thread.prepend(db, "whatsapp", CHAT, [{"messageId": "x", "body": "x", "ts": 1.0}], complete=True)
    for i in range(thread.KEEP + 2):
        thread.append(db, "whatsapp", CHAT, {"messageId": f"n{i}", "body": "n", "ts": 10.0 + i}, "in")
    assert len(thread.window(db, "whatsapp", CHAT)) == thread.KEEP
    assert thread.meta(db, "whatsapp", CHAT)["complete"] is False


def test_old_conversations_are_pruned_but_recent_ones_are_not():
    from widgets.mensajeria import thread
    db = {}
    thread.append(db, "whatsapp", "viejo", {"messageId": "a", "body": "a", "ts": 1.0}, "in")
    thread.append(db, "whatsapp", "nuevo", {"messageId": "b", "body": "b", "ts": 1.0}, "in")
    db["threads"][thread.key("whatsapp", "viejo")]["touched"] = time.time() - (thread.DAYS + 1) * 86400
    assert thread.prune(db) == 1
    assert thread.window(db, "whatsapp", "nuevo") and not thread.window(db, "whatsapp", "viejo")


def test_a_conversation_survives_days_which_is_the_whole_point():
    from widgets.mensajeria import thread
    db = {}
    thread.append(db, "whatsapp", CHAT, {"messageId": "a", "body": "a", "ts": 1.0}, "in")
    db["threads"][thread.key("whatsapp", CHAT)]["touched"] = time.time() - (thread.DAYS - 1) * 86400
    assert thread.prune(db) == 0
    assert thread.window(db, "whatsapp", CHAT)


def test_at_least_twenty_messages_per_chat_are_kept():
    """The operator's stated floor. A ceiling below it would make the feature not the feature he asked for."""
    from widgets.mensajeria import thread
    assert thread.KEEP >= 20
    assert thread.DAYS >= 3
