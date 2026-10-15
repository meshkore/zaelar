"""A reply with nothing to answer says nothing was sent (use case dictate-a-reply-honestly, 2026-10-15).

«Respóndele a Marta por WhatsApp que llego a las nueve» with no chat of hers and WhatsApp unlinked: the model called
`reply_message` (n=1), `mensajeria:reply` found nothing to answer and returned the card's whole state — a success
in shape — and the turn said «Hecho.». What leaves the machine is never claimed without the act: the reply is now a
refusal that names what is missing (no conversation; which channels are not connected) and the way out.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def card(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data
    return data


def test_a_reply_to_a_conversation_that_is_not_there_is_refused_and_says_why(card):
    out = card.apply_action("reply", {"n": 1, "text": "Marta, llego a las nueve"})
    assert out.get("ok") is False and str(out.get("error")).startswith("no_target"), out
    assert "no se ha enviado nada" in out["message"] and "WhatsApp" in out["message"]
    assert not card.load_db().get("pending_reply")
    from nucleo.flash import refusal_line
    assert refusal_line.speakable("mensajeria", out) == out["message"]      # every word of it reaches his ear


def test_a_reply_with_no_target_named_is_refused_too(card):
    assert card.apply_action("reply", {"text": "on my way"}).get("ok") is False


def test_a_reply_with_no_words_still_queues_nothing_and_claims_nothing(card):
    out = card.apply_action("reply", {"n": 1, "text": "  "})
    assert out.get("ok") is not False and not card.load_db().get("pending_reply")
