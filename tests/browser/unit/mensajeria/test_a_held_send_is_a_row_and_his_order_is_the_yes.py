"""V2-800 — a send held for his word is a ROW of the mail card, a send for later is a scheduled row, and his explicit
order over a draft he has SEEN is the confirmation — decided by the one consent rule, the same for every channel.

The class (live, 2026-10-26): he asked for an email with exact text, «show it to me and wait for my "send it"». It
was shown in a document; the mail card knew nothing about it. His «send it» resolved to `send_draft` over whatever
reply draft was newest (or none), was asked TWICE (chat and a card overlay), and his yes sent nothing. Generic by
construction: email and WhatsApp below, an address and a contact, Spanish and English text.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from nucleo import consent
from nucleo.acts import message as held_send
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
    # Process state the gate tests leave behind (the disarm leaves a pending question ON PURPOSE): a later voice
    # turn in the same process answered it instead of closing its card.
    from nucleo import his_words as _hw, untrusted
    from widgets import confirm as wc
    wc.reset()
    untrusted.reset()
    _hw.reset()


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


def _worker_door(monkeypatch):
    """The REAL door a send crosses since V2-852 M2 — the turn routes it as a task and the worker's act goes through
    `worker_api.worker_act` → `exit_gate.gate` → the one asker; only the transport to the card is the real card's
    own `apply_action`, so what «left» is the card's outbox."""
    from types import SimpleNamespace

    from nucleo.cli import worker_api, worker_api_answer
    from widgets import server_api
    sent = []

    async def _brain_action(wid, act, payload):
        sent.append((wid, act, dict(payload)))
        return data.apply_action(act, dict(payload))
    monkeypatch.setattr(server_api, "brain_action", _brain_action)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    rec = SimpleNamespace(task_id="held", playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="",
                          surface="", sheet="", native_sid="", waiting_on="", ask="", ask_corr="", parked=False,
                          mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api_answer, "_record_for", lambda _e: rec)

    def act(payload):
        import json
        out = asyncio.run(worker_api.worker_act(task_id="held", token="t", action="widget_data", payload={
            "widget_id": "mensajeria", "action": "send_draft", "payload": dict(payload)}))
        return json.loads(out.body)

    return SimpleNamespace(api=worker_api, act=act, sent=sent, rec=rec)


_QUINN = {"contact": "quinn@example.com"}


def _quinn_draft(text="Hi Quinn, Thursday at ten works for us."):
    data.apply_action("draft", {"contact": "quinn@example.com", "subject": "Thursday", "text": text})


def _left():
    return [(o["to"], o.get("subject")) for o in (data.load_db().get("pending_send") or [])]


def test_an_unsure_order_over_a_held_draft_is_asked_once_and_his_yes_sends_that_one_row(monkeypatch):
    """«Asked once, in one place» through the real door: the unsure order (no sure order recorded by the turn) is ONE
    durable question with the act retained and nothing sent; his yes sends exactly that draft; a second answer finds
    no question left."""
    d = _worker_door(monkeypatch)
    from nucleo.cli import worker_api_answer
    monkeypatch.setattr(worker_api_answer, "_says_yes", lambda *_a: True)
    _quinn_draft()
    got = d.act(_QUINN)
    assert got.get("status") == "pending" and d.sent == [] and not _left(), got
    assert asyncio.run(d.api.answer(got["corr_id"], "yes, send it", resume=False))
    assert _left() == [("quinn@example.com", "Thursday")]
    assert not asyncio.run(d.api.answer(got["corr_id"], "yes", resume=False)), "a second answer found a question"
    assert len(d.sent) == 1


@pytest.mark.parametrize("text", ["Hi Quinn, Thursday at ten works for us.", "Hola Quinn, el jueves a las diez nos va bien."])
def test_his_sure_order_over_the_draft_he_saw_is_the_yes_at_the_worker_door(monkeypatch, text):
    """CRIT-C9 where the send now runs: the turn that routed his «send it» recorded its sure order over THAT row
    (`message.note_his_order`), and the worker's exit door reads it with no brief — nothing is asked, the row leaves."""
    d = _worker_door(monkeypatch)
    _quinn_draft(text)
    assert held_send.note_his_order("mensajeria", "send_draft", _QUINN, _brief("mensajeria:send_draft", 0.95))
    got = d.act(_QUINN)
    assert got.get("ok") and got.get("status") != "pending", got
    assert _left() == [("quinn@example.com", "Thursday")]


def test_a_draft_edited_after_his_order_is_another_row_and_is_asked(monkeypatch):
    d = _worker_door(monkeypatch)
    _quinn_draft()
    held_send.note_his_order("mensajeria", "send_draft", _QUINN, _brief("mensajeria:send_draft", 0.95))
    _quinn_draft("Hi Quinn, actually Friday at noon.")
    assert d.act(_QUINN).get("status") == "pending" and d.sent == []


def test_an_unsure_order_records_nothing(monkeypatch):
    _quinn_draft()
    assert not held_send.note_his_order("mensajeria", "send_draft", _QUINN, _brief("mensajeria:send_draft", 0.40))


def test_disarmed_the_order_the_turn_recorded_does_not_reach_the_worker_and_he_is_asked_again(monkeypatch):
    """Disarm: the worker door reads no recorded order (the state the move to the worker left, V2-852 M2) → his
    «send it» over the draft he saw is asked a second time."""
    d = _worker_door(monkeypatch)
    _quinn_draft()
    held_send.note_his_order("mensajeria", "send_draft", _QUINN, _brief("mensajeria:send_draft", 0.95))
    from nucleo.acts import message_held
    monkeypatch.setattr(message_held, "_HIS_ORDERS", {})
    assert d.act(_QUINN).get("status") == "pending" and d.sent == [], "the disarm did not take"


def test_a_pending_confirmation_has_one_surface_the_conversation():
    """«La confirmación se pide UNA vez, en UN sitio»: the chat thread holds the Yes/No (answerable there or by
    voice — both resolve the same pending row); the card overlay that repeated it is gone.

    Kept as a SOURCE check on purpose: which surface paints the question is `sse.js` routing, which cannot be
    driven from Python (the module pulls the store and the UI in at import). Its behaviour half — one row, one
    question emitted, either channel resolves it — is the test above."""
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
