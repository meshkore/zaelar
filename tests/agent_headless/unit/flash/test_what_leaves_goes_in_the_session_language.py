"""What LEAVES goes in the session's language — a note to Quinn is not written in the manifest's (demo pass 106).

E3 «send the invoice to quinn, tell him we're already trying inworld and he should book it», in an English
session, three passes running: «Ya estamos probando Inworld, así que adelante con la reserva.» The model reads
`forward`'s description in Spanish («mándale a Quinn la factura…») and copies it; the prompt's language lock
(2.230) was not enough. An outgoing text in the OTHER of the two product languages is translated once before
it is sent; one already in his language, or with no words to tell, is untouched.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def ol(monkeypatch):
    from nucleo.flash import outgoing_lang, fast_client
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: "en")
    calls = []

    class _FC:
        async def complete(self, messages, **_kw):
            calls.append(messages[-1]["content"])
            return "We're already trying Inworld, so go ahead and book it."
    monkeypatch.setattr(fast_client, "FastClient", _FC)
    monkeypatch.setattr(outgoing_lang, "LIVE", True)        # the client is faked: the door may call it
    outgoing_lang._calls = calls
    return outgoing_lang


def _run(ol, payload, wid="mensajeria", action="forward"):
    return asyncio.run(ol.in_session_language(wid, action, payload))


def test_a_spanish_note_in_an_english_session_is_translated(ol):
    p = _run(ol, {"contact": "quinn", "text": "Ya estamos probando Inworld, así que adelante con la reserva."})
    assert p["text"] == "We're already trying Inworld, so go ahead and book it." and p["contact"] == "quinn"


def test_an_english_note_is_left_alone(ol):
    p = {"contact": "Rowan", "text": "Hey Rowan! Small change: our catch up tomorrow moves to 5:00 PM. See you then!"}
    assert _run(ol, p, action="send_to") == p and not ol._calls


def test_an_act_that_does_not_leave_is_left_alone(ol):
    p = {"title": "Reunión con el equipo de la oficina"}
    assert _run(ol, p, wid="agenda", action="add_meeting") == p and not ol._calls


def test_too_few_words_to_tell_is_left_alone(ol):
    p = {"contact": "quinn", "text": "Gracias"}
    assert _run(ol, p) == p and not ol._calls


def test_the_shared_send_door_passes_through_it():
    import inspect
    from nucleo.flash import data_ops
    assert "in_session_language" in inspect.getsource(data_ops.dispatch_and_report)
