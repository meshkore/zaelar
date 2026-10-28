"""V2-807 T-09 — a message to someone has ONE body: a version of a held draft written on another card lands on the row.

The class (live, 2026-10-26): a held email was copied into a document sheet; every spoken correction rewrote the copy
and was marked done against the document's own field; «send it» sent the row — the original text nobody corrected.

Generic by construction: the claim measures overlap with the held draft (and its recipient address), never the
meaning of a word — Spanish and English bodies below, an address in the title and none at all, and a document that
only MENTIONS the address is not a draft.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from widgets import store as wstore
from widgets import text_home
from widgets.mensajeria import data, held

ES_ORIGINAL = ("Hola,\n\nSomos Zaelar, un asistente de voz que gestiona reservas de restaurante en nombre de sus "
               "usuarios. Queremos solicitar acceso a la API de reservas para integrarnos directamente con vuestra "
               "plataforma y evitar el navegador.\n\nUn saludo,\nEl equipo de Zaelar")
ES_CORRECTED = ("Hola, equipo:\n\nSomos Zaelar, un asistente de voz que gestiona reservas de restaurante en nombre de "
                "sus usuarios. Queremos solicitar acceso a la API de reservas para integrarnos directamente con "
                "vuestra plataforma.\n\nUn saludo,\nEl equipo de Zaelar\nTel. 600 000 000 · zaelar.example")
EN_ORIGINAL = ("Hi Rowan,\n\nFollowing up on the venue booking for Thursday: could you confirm the deposit amount "
               "and whether the terrace is still available for twelve guests?\n\nThanks")
EN_CORRECTED = ("Hi Rowan,\n\nFollowing up on the venue booking for Thursday evening: could you confirm the deposit "
                "amount and whether the terrace is available for fourteen guests?\n\nThanks a lot")
UNRELATED_REPORT = ("# Restaurant booking platforms\n\nA comparison of the booking APIs on the market: who offers "
                    "partner access, the documentation quality, the latency of availability calls and pricing.")


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan Pike", "phone": "+34600111222"})
    cd.apply_action("set_channel", {"contactId": "c1", "platform": "whatsapp", "handle": "+34600111222"})
    yield


def _hold_email(text=ES_ORIGINAL):
    out = data.apply_action("draft", {"contact": "partners@booking.example", "subject": "API access", "text": text})
    assert out["ok"] and out["held"], out
    return out["key"]


# ── the claim: a version of the held draft, in any language; a mention is not a version ─────────────────────

def test_a_corrected_copy_of_a_held_email_is_claimed_by_its_row():
    key = _hold_email()
    got = held.claim(data.load_db(), ES_CORRECTED, "Borrador")
    assert got and got["action"] == "save_draft" and got["payload"] == {"key": key, "text": ES_CORRECTED}


def test_an_english_version_of_a_held_whatsapp_is_claimed_too():
    out = data.apply_action("draft", {"contact": "Rowan Pike", "text": EN_ORIGINAL})
    assert out["ok"], out
    got = held.claim(data.load_db(), EN_CORRECTED, "")
    assert got and got["payload"]["key"] == out["key"]


def test_a_document_that_only_names_the_recipient_is_not_the_draft():
    _hold_email()
    assert held.claim(data.load_db(), UNRELATED_REPORT, "Notes for partners@booking.example") is None


def test_with_nothing_held_nothing_is_claimed():
    assert held.claim(data.load_db(), ES_CORRECTED, "") is None
    assert text_home.route("documento", "show", {"title": "x", "body": ES_CORRECTED}) is None


# ── the door: documento:show of the held message writes the row; any other write is untouched ────────────────

def test_the_door_turns_a_document_show_of_the_held_message_into_its_row():
    key = _hold_email()
    home = text_home.route("documento", "show", {"title": "Correo a partners@booking.example", "body": ES_CORRECTED})
    assert home == {"widget": "mensajeria", "action": "save_draft", "payload": {"key": key, "text": ES_CORRECTED},
                    "from": "documento:show", "to": "partners@booking.example", "why": home["why"]}
    # an action that declares no free-text field is never rerouted, whatever it carries
    assert text_home.route("documento", "goto", {"text": ES_CORRECTED}) is None
    assert text_home.route("mensajeria", "draft", {"text": ES_CORRECTED}) is None


def test_the_turn_door_brings_the_draft_card_through_the_one_canvas_door():
    _hold_email()
    shown, events = [], []
    wid, action, payload = text_home.redirect(
        "documento", "show", {"title": "x", "body": ES_CORRECTED},
        emit=lambda *a, **k: events.append((a, k)), present=lambda w, **k: shown.append((w, k["reason"])))
    assert (wid, action) == ("mensajeria", "save_draft") and payload["text"] == ES_CORRECTED
    assert shown == [("mensajeria", "turn-order")]
    assert events and events[0][1]["extra"]["from"] == "documento:show", "the redirect is recorded"


def test_the_harness_checks_the_row_card_not_the_copy():
    """«correct the draft» is attested on the card that holds the row: the redirected op is what the turn records."""
    from nucleo.circuit import compose as write_harness
    _hold_email()
    wid, action, _p = text_home.redirect("documento", "show", {"title": "x", "body": ES_CORRECTED})
    assert write_harness.writes_of([(wid, action)]) == [("mensajeria", "save_draft")]


# ── end to end: a correction written as a document, then «send it» — the corrected body is what leaves ───────

def test_the_body_that_leaves_is_the_one_he_corrected():
    from widgets import server_api
    _hold_email()
    res = asyncio.run(server_api._dispatch("documento", "show", {"title": "Borrador", "body": ES_CORRECTED}))
    assert res.get("ok") is not False, res
    from widgets.documento import data as doc
    assert doc.view_data()["empty"], "the copy is never written: the text went to the row"
    assert held.held(data.load_db())[0]["text"] == ES_CORRECTED
    time.sleep(0.01)
    sent = data.apply_action("send_draft", {"contact": "partners@booking.example"})
    assert sent["ok"], sent
    assert [o["text"] for o in data.load_db()["pending_send"]] == [ES_CORRECTED]


def test_a_document_that_is_not_a_message_still_lands_on_the_sheet():
    from widgets import server_api
    _hold_email()
    res = asyncio.run(server_api._dispatch("documento", "show", {"title": "Platforms", "body": UNRELATED_REPORT}))
    assert res.get("ok"), res
    from widgets.documento import data as doc
    assert doc.view_data()["body"] == UNRELATED_REPORT
    assert held.held(data.load_db())[0]["text"] == ES_ORIGINAL
