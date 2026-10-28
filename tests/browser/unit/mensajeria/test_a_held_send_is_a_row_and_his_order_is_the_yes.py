"""V2-800 — a send held for his word is a ROW of the mail card, a send for later is a scheduled row, and his explicit
order over a draft he has SEEN is the confirmation — decided by the one consent rule, the same for every channel.

The class (live, 2026-10-26): he asked for an email with exact text, «show it to me and wait for my "send it"». It
was shown in a document; the mail card knew nothing about it. His «send it» resolved to `send_draft` over whatever
reply draft was newest (or none), was asked TWICE (chat and a card overlay), and his yes sent nothing. Generic by
construction: email and WhatsApp below, an address and a contact, Spanish and English text.
"""
from __future__ import annotations

import threading
import time

import pytest

from nucleo import consent
from widgets import store as wstore
from widgets.mensajeria import data, held


def _brief(target: str, conf: float, kind: str = "order") -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {"screen_action": {"choice": target, "confidence": conf},
                       "request_type": {"choice": kind, "confidence": 1.0}}}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan Pike", "phone": "+34600111222"})
    cd.apply_action("set_channel", {"contactId": "c1", "platform": "whatsapp", "handle": "+34600111222"})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    # His turns: one arrives AFTER the draft is written (he has seen it) unless a test says otherwise.
    from nucleo import his_words
    monkeypatch.setattr(his_words, "since", lambda ts: ["send it"] if ts < time.time() + 1 else [])
    yield
    consent._reset_for_tests()


def _held_email():
    return data.apply_action("draft", {"contact": "hospitality@example.com", "subject": "API access",
                                       "text": "Hola,\n\nQueremos integrarnos con vuestra API."})


# ── the held draft is a row; nothing leaves when it is written ───────────────────────────────────────────

def test_a_new_message_held_for_his_word_is_a_draft_row_and_nothing_leaves():
    out = _held_email()
    assert out["ok"] and out["held"] and "revísalo" in out["message"]
    db = data.load_db()
    assert not db.get("pending_send"), "writing the draft must not send it"
    rows = held.held(db)
    assert rows[0]["to"] == "hospitality@example.com" and rows[0]["subject"] == "API access"
    assert "BORRADOR esperando su OK" in data.__dict__["_held"].prompt_lines(db)[0]


def test_send_draft_named_by_its_recipient_sends_that_draft_with_its_subject():
    _held_email()
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})   # a second held draft, newer
    out = data.apply_action("send_draft", {"contact": "hospitality@example.com"})
    assert out["ok"], out
    q = data.load_db()["pending_send"]
    assert [(o["to"], o.get("subject")) for o in q] == [("hospitality@example.com", "API access")]
    assert [d["to"] for d in held.held(data.load_db())] == ["Rowan Pike"], "only the sent draft is gone"


# ── a send for later is a scheduled row: held until its time, visible, cancellable ─────────────────────

def test_a_send_for_later_waits_is_visible_and_is_cancelled():
    from connectors.messaging import store as msgstore
    _held_email()
    out = data.apply_action("send_draft", {"contact": "hospitality", "in_minutes": 600})
    assert out["ok"] and out["scheduled_for"] > time.time() + 590 * 60
    assert msgstore.take_pending_send() == [], "a scheduled send must not leave before its time"
    sent = data.view_data()["sent"]
    assert any(r.get("scheduled_for") for r in sent)
    assert any("PROGRAMADO" in l for l in held.prompt_lines(data.load_db()))
    assert data.apply_action("cancel_send", {})["ok"]
    assert not held.scheduled(data.load_db())


def test_an_unreadable_time_is_refused_not_sent_now():
    _held_email()
    out = data.apply_action("send_draft", {"contact": "hospitality", "at": "tonight-ish"})
    assert not out["ok"] and out["error"] == "bad_time"
    assert not data.load_db().get("pending_send")


# ── his order over a SEEN draft is the yes — one rule, every channel ───────────────────────────────────

def test_an_explicit_send_over_a_seen_draft_is_the_confirmation(monkeypatch):
    """The live shape: a stranger's mail sat in the context, so the leave gate asked even after he had read the
    draft and said «send it». The row he SAW names its recipient and its text; his sure order is the yes."""
    from nucleo import untrusted
    from nucleo.acts import message as held_send
    from nucleo.acts import message as leave_gate
    from nucleo.flash import frontend
    from widgets import actions as wa
    monkeypatch.setattr(untrusted, "present", lambda *a, **k: True)
    _held_email()
    payload = {"contact": "hospitality@example.com"}
    sure = _brief("mensajeria:send_draft", 0.91)
    assert held_send.confirmed("mensajeria", "send_draft", payload, sure)
    assert not leave_gate.needs_asking(sure, "mensajeria", "send_draft", payload=payload, said="send it")
    assert leave_gate.needs_asking(_brief("mensajeria:send_draft", 0.5), "mensajeria", "send_draft",
                                   payload=payload, said="send it"), "an unsure order still asks, once"
    assert frontend.action_mode_now("mensajeria", "send_draft", payload) in (wa.FAST, wa.CONFIRM)
    assert held_send.release(wa.CONFIRM, "mensajeria", "send_draft", payload, sure) == wa.FAST, \
        "his explicit order over the draft he saw is the yes — asked once, not again"
    assert held_send.release(wa.CONFIRM, "mensajeria", "send_draft", payload,
                             _brief("mensajeria:send_draft", 0.5)) == wa.CONFIRM


def test_his_yes_clears_the_class_rail_and_never_his_own_ask_rule():
    lvl = {"level": "sensitive", "policy_key": "messaging.reply"}
    import rules
    rules.add(rules.GLOBAL, "gate", "ask_at", "sensitive")          # his global «ask before sensitive acts»
    assert consent.asks(consent.decide(**lvl))
    assert not consent.asks(consent.decide(**lvl, his_yes=True))
    consent.set_class("messaging.reply", "ask")
    assert consent.asks(consent.decide(**lvl, his_yes=True))


def test_a_draft_he_has_not_seen_or_an_unsure_order_is_not_a_yes(monkeypatch):
    from nucleo import his_words
    from nucleo.acts import message as held_send
    _held_email()
    payload = {"contact": "hospitality@example.com"}
    assert not held_send.confirmed("mensajeria", "send_draft", payload, _brief("mensajeria:send_draft", 0.5))
    monkeypatch.setattr(his_words, "since", lambda ts: [])        # written in this very turn: never seen
    assert not held_send.confirmed("mensajeria", "send_draft", payload, _brief("mensajeria:send_draft", 0.95))


def test_his_rule_for_one_channel_governs_that_channel_only():
    """«pregúntame siempre antes de mandar un correo» — the email asks, the WhatsApp to Rowan does not."""
    from nucleo.acts import message as held_send
    _held_email()
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})
    consent.set_class("messaging.send_new@email", "ask")
    email = {"contact": "hospitality@example.com"}
    wa_msg = {"contact": "Rowan Pike"}
    assert not held_send.confirmed("mensajeria", "send_draft", email, _brief("mensajeria:send_draft", 0.95))
    assert held_send.confirmed("mensajeria", "send_draft", wa_msg, _brief("mensajeria:send_draft", 0.95))
    assert consent.class_policy("messaging.send_new@whatsapp") == "allow", "falls back to the bare class"


def test_the_same_inputs_give_every_channel_the_same_decision():
    for chan in ("email", "whatsapp", "telegram"):
        v = consent.decide(level="sensitive", policy_key=f"messaging.send_new@{chan}")
        assert v["verdict"] == consent.RUN, chan
        consent.set_class(f"messaging.send_new@{chan}", "ask")
        assert consent.asks(consent.decide(level="sensitive", policy_key=f"messaging.send_new@{chan}", his_yes=True))


def test_a_pending_confirmation_has_one_surface_the_conversation():
    """«La confirmación se pide UNA vez, en UN sitio»: the chat thread holds the Yes/No (answerable there or by
    voice — both resolve the same pending row); the card overlay that repeated it is gone."""
    import pathlib
    sse = (pathlib.Path(__file__).resolve().parents[4] / "frontend/app/services/sse.js").read_text(encoding="utf-8")
    block = sse[sse.index('else if (d.label === "confirm" && d.id) {'):][:900]
    assert "store.setWidgetConfirm(" in block
    assert "desktop.showConfirm(" not in block


def test_a_new_message_is_keyed_by_who_it_goes_to_never_by_an_empty_chat():
    """Two NEW messages to two people with no conversation yet must be two drafts — keyed by recipient."""
    _held_email()
    data.apply_action("draft", {"contact": "Rowan Pike", "text": "See you at 4"})
    keys = sorted(data.load_db()["drafts"])
    assert keys == ["to:email:hospitality@example.com", "to:whatsapp:+34600111222"], keys
