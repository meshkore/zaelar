"""V2-683 row 2 — the door that OPENS a conversation, and what it refuses to do.

Every outbound path in this widget until now answered something that had already arrived: `reply`, `draft`
and `send_draft` all resolve against a stored item or the open thread. «Contacta con Iván Musikin» had no
door at all, and that is what this adds.

The asymmetry that shapes every case below: a reply can only say the wrong thing to the RIGHT person,
because the conversation it answers is the address. This door can say the right thing to the WRONG person,
and no apology takes that back — so the refusals carry most of the weight, and each one names what is
missing so the next attempt can succeed instead of asking the operator the same thing twice.
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def box(tmp_path, monkeypatch):
    """ISOLATED stores — the messaging queue and the directory both live under widgets/_data."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    cd.apply_action("add_contact", {"name": "Iván Musikin", "email": "ivan@example.com"})
    cid = cd.load_db()["contacts"][0]["id"]
    cd.apply_action("set_channel", {"contactId": cid, "platform": "telegram", "handle": "@ivanm"})
    return md


def _q(payload):
    from voice.engine.llm.providers.confirm_gate import _human_confirm_question
    return _human_confirm_question("mensajeria", "send_to", payload)


# ── it sends ─────────────────────────────────────────────────────────────────────────────────────────────

def test_it_goes_out_by_his_PREFERRED_channel_without_being_told_which(box):
    r = box.apply_action("send_to", {"contact": "Iván", "text": "¿Te va bien esta tarde?"})
    assert r["ok"] and r["result"]["channel"] == "telegram"
    order = box.load_db()["pending_send"][0]
    assert order["to"] == "@ivanm" and order["text"] == "¿Te va bien esta tarde?"


def test_the_order_carries_a_REF_and_the_errand_it_belongs_to(box):
    """The ref is what ties this send to the conversation the connector is about to create — and through
    that, to whatever asked for it. Without it a new thread belongs to nobody."""
    box.apply_action("send_to", {"contact": "Iván", "text": "hola", "objective": "organizar una reunión"})
    order = box.load_db()["pending_send"][0]
    assert order["ref"] and order["objective"] == "organizar una reunión"
    assert order["contactId"]


def test_an_ADDRESS_said_out_loud_needs_no_contact(box):
    """«Manda un correo a reservas@…» is a real errand with nobody behind it, and an address is a complete
    way to reach somebody."""
    r = box.apply_action("send_to", {"contact": "reservas@hotel.com", "text": "¿Tenéis mesa?"})
    assert r["ok"] and r["result"]["channel"] == "email"
    assert box.load_db()["pending_send"][0]["to"] == "reservas@hotel.com"


def test_the_channel_he_NAMES_wins_over_the_preferred_one(box):
    r = box.apply_action("send_to", {"contact": "Iván", "text": "hola", "channel": "email"})
    assert r["ok"] and r["result"]["channel"] == "email"


# ── it refuses ───────────────────────────────────────────────────────────────────────────────────────────

def test_TWO_people_of_that_name_stops_and_names_them(box):
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Javi", "city": "Soria", "email": "a@x.com"})
    cd.apply_action("add_contact", {"name": "Javi", "city": "Madrid", "email": "b@x.com"})
    r = box.apply_action("send_to", {"contact": "Javi", "text": "hola"})
    assert r["ok"] is False
    assert "Soria" in r["error"] and "Madrid" in r["error"]
    assert not box.load_db()["pending_send"]


def test_somebody_we_do_not_have_is_not_invented(box):
    r = box.apply_action("send_to", {"contact": "Pablo Sabin", "text": "hola"})
    assert r["ok"] is False and "no tengo a" in r["error"]
    assert "set_channel" in r["error"] or "add_contact" in r["error"]
    assert not box.load_db()["pending_send"]


def test_a_channel_he_does_not_have_names_the_ones_he_DOES(box):
    """«Mándale un WhatsApp» to somebody whose number we never had: the refusal is only useful if it says
    what we do have, or the next turn asks the operator for something he already told us."""
    r = box.apply_action("send_to", {"contact": "Iván", "text": "hola", "channel": "whatsapp"})
    assert r["ok"] is False and "Telegram" in r["error"]


def test_a_message_with_no_TEXT_is_not_sent(box):
    r = box.apply_action("send_to", {"contact": "Iván"})
    assert r["ok"] is False and "`text`" in r["error"]


def test_an_unknown_CHANNEL_is_refused_before_anything_else(box):
    """It has to be refused for what it IS — a channel this engine does not have — and not as a side effect
    of the recipient lookup. With an address (which needs no contact at all) the lookup cannot refuse
    anything, so this is the case where only the channel check can answer: without it the operator is told
    «no tengo a reservas@hotel.com en el directorio», which sends the next turn hunting for the wrong thing."""
    r = box.apply_action("send_to", {"contact": "reservas@hotel.com", "text": "hola", "channel": "signal"})
    assert r["ok"] is False and "signal" in r["error"]
    assert "directorio" not in r["error"]
    # and the same refusal for somebody we DO have
    assert box.apply_action("send_to", {"contact": "Iván", "text": "hola",
                                        "channel": "signal"})["ok"] is False


def test_the_veto_runs_BEFORE_the_order_reaches_the_owner(box):
    """`answer_action` is the read-only hook the backed route consults; `{"ok": False}` stops the enqueue.
    Without it an unresolvable send would sit in the owner's mailbox and fail out of sight."""
    assert box.answer_action("send_to", {"contact": "Pablo Sabin", "text": "hola"})["ok"] is False
    assert box.answer_action("send_to", {"contact": "Iván", "text": "hola"})["ok"] is True
    assert not box.load_db().get("pending_send")      # the hook must never write


# ── what the operator hears before anything leaves ───────────────────────────────────────────────────────

def test_the_question_names_WHO_by_WHICH_app_and_WHAT(box):
    q = _q({"contact": "Iván", "text": "¿Te va bien esta tarde?"})
    assert "Iván Musikin" in q and "Telegram" in q and "¿Te va bien esta tarde?" in q


def test_with_an_objective_the_question_IS_the_mandate(box):
    """One yes authorises the exchange that follows, said out loud — instead of asking again per message."""
    q = _q({"contact": "Iván", "text": "hola", "objective": "organizar una reunión esta tarde"})
    assert "organizar una reunión esta tarde" in q
    assert "sigo yo la conversación" in q


def test_without_an_objective_it_promises_NOTHING_of_the_sort(box):
    q = _q({"contact": "Iván", "text": "hola"})
    assert "sigo yo" not in q


def test_the_question_never_recites_the_manifest_prose(box):
    """V2-665: the `desc` is written for the model, and reading it aloud is what he once had to listen to."""
    q = _q({"contact": "Iván", "text": "hola"})
    assert "directorio de contactos" not in q and "reply" not in q


# ── the last door: nothing leaves carrying a secret ──────────────────────────────────────────────────────

def test_a_text_carrying_a_SECRET_never_leaves(box):
    from widgets.mensajeria import owner
    clean, leaked = owner._scrub("la contraseña del wifi es Patata1234!! por si acaso")
    assert leaked, "a secret in a model-composed message to a third party must stop the send"


def test_an_ordinary_message_is_not_held_back(box):
    from widgets.mensajeria import owner
    assert owner._scrub("Hola Iván, soy el asistente de Ricart. ¿Te va bien a las seis?")[1] == ""


def test_a_scan_that_could_not_RUN_stops_the_send(box, monkeypatch):
    """Fails closed on purpose: «I could not check» is not «it is fine» when the reader is a stranger."""
    import builtins
    real = builtins.__import__

    def boom(name, *a, **k):
        if name == "memory.secrets" or (name == "memory" and "secrets" in (a[2] or ())):
            raise ImportError("no")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", boom)
    from widgets.mensajeria import owner
    assert owner._scrub("hola")[1] != ""


# ── the shape of the wire ────────────────────────────────────────────────────────────────────────────────

def test_a_phone_becomes_the_id_whatsapp_addresses_people_by(box):
    """A conversation opened by number must key the SAME as one that arrived on its own, or the thread
    splits in two and the operator sees the same person twice."""
    from connectors.whatsapp.service import _jid
    assert _jid("+34 600 111 222") == "34600111222@s.whatsapp.net"
    assert _jid("34600111222@s.whatsapp.net") == "34600111222@s.whatsapp.net"
    assert _jid("") == ""


def test_the_manifest_declares_it_and_does_NOT_ask_again(box):
    """⚠️ This gate was flipped in V2-692 and the test was not brought along — a red left standing since
    2026-09-14, found by the next batch's full sweep.

    The operator's rule, in his own words: «hay una regla de que no se contestan a mensajes, pero si yo
    específicamente digo que se haga una acción y eso requiere mandar un mensaje, obviamente ese permiso
    pasa ya por hecho». `reply` KEEPS its confirm — answering somebody who wrote to him is the engine
    speaking on its own initiative. `send_to` is the opposite case by construction: it only exists because
    he asked for the gestión, so asking again is asking twice, and the live run measured what that costs —
    he had to drive every step by hand and the errand never started. The contract that replaces the gate is
    `objective`: nothing goes out through this door without saying what it is trying to achieve.
    """
    m = json.loads((ENGINE / "widgets" / "mensajeria" / "manifest.json").read_text(encoding="utf-8"))
    a = m["actions"]["send_to"]
    assert a["confirm"] is False, "he already gave the order; a second ask is the one that stalled the errand"
    assert set(a["payload"]) >= {"contact", "text", "channel", "objective"}
    assert m["actions"]["reply"]["confirm"] is True, \
        "and the OTHER door keeps its gate — this is not a blanket opening of the mouth"


def test_answering_a_conversation_still_works_exactly_as_before(box):
    """The extraction that paid for this door moved `reply`'s target resolution into `outbound.py`. The
    claim it has always made is measured here so the move cannot quietly change it."""
    from widgets import store
    db = box.load_db()
    db["items"] = [{"n": 1, "platform": "email", "chatId": "ana@x.com", "messageId": "uid-1",
                    "senderId": "ana@x.com", "from": "Ana", "subject": "Reunión", "msgid": "<m1>",
                    "dir": "in", "body": "¿Confirmamos?", "ts": 1}]
    store.save(box.WIDGET_ID, db)
    box.apply_action("reply", {"n": 1, "text": "Sí, confirmado"})     # returns the view, as it always has
    queued = box.load_db()["pending_reply"]
    assert len(queued) == 1 and queued[0]["to"] == "ana@x.com"
    assert queued[0]["text"] == "Sí, confirmado" and queued[0]["msgid"] == "<m1>"
