"""Who a send goes to is never a doubt — the one filter for acts that leave (the operator, 2026-10-15).

> «No podemos dejar con una duda quién es el destinatario de un email o de una reunión o de un mensaje, porque esos
> son unos asuntos que deben levantar un flag de confirmación de usuario […] un filtro único que básicamente es de
> evitar comprometer al usuario.»

Everything that does not leave runs on the operator's 70% with no permission question. An act that leaves the
machine (declared `external.send`) runs only when its recipient is certain:

  · named in HIS words, this turn or his recent ones — otherwise the leave gate asks «¿se lo mando a X?»;
  · resolved by the directory exactly, never by spelling tolerance — a near name is named back as a question;
  · and the engine never turns the model's draft into a send to somebody he did not name.

The meeting invitation is such an act too, so it declares `external.send` and walks through the same filter.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def gate(monkeypatch):
    from nucleo import his_words, untrusted
    from nucleo.flash import leave_gate
    his_words.reset()
    monkeypatch.setattr(untrusted, "present", lambda: False)
    yield leave_gate
    his_words.reset()


def test_a_recipient_he_never_named_is_asked_even_with_no_stranger_in_the_context(gate):
    from widgets import actions as wa
    from nucleo.flash import frontend
    assert frontend.at_least_sensitive("mensajeria", "send_to")
    assert gate.asked_if_leaving(wa.FAST, None, "mensajeria", "send_to", payload={"contact": "Quinn"},
                                 said="send the summary to the team") == wa.CONFIRM
    assert gate.asked_if_leaving(wa.FAST, None, "mensajeria", "send_to", payload={"contact": "Rowan"},
                                 said="send rowan a telegram with the new time") == wa.FAST


def test_a_recipient_he_named_a_moment_ago_is_his(gate):
    """«book a catch up with Ethan» … «telegram him the new time»: the person is his from the conversation."""
    from nucleo import his_words
    his_words.note("find me a free slot tomorrow afternoon to talk with Ethan")
    assert gate.unnamed_recipients("mensajeria", "send_to", {"contact": "Ethan"}, "telegram him the new time") == []
    assert gate.unnamed_recipients("mensajeria", "send_to", {"contact": "Quinn"}, "telegram him the new time") == ["Quinn"]


def test_an_act_that_does_not_name_anybody_is_not_asked(gate):
    """A reply goes to whoever wrote: no WHO, nothing to doubt."""
    assert gate.unnamed_recipients("mensajeria", "reply", {"text": "on my way"}, "tell him I'm on my way") == []


def test_the_meeting_invitation_leaves_and_its_guest_must_be_his(gate):
    from widgets import effects
    assert effects.carries("agenda", "invite", effects.EXTERNAL_SEND)
    assert gate.unnamed_recipients("agenda", "invite", {"who": "Paco Pérez"}, "invite him to the meeting") == ["Paco Pérez"]
    assert gate.unnamed_recipients("agenda", "invite", {"who": "Paco Pérez"}, "invite paco to the meeting") == []


def test_the_engine_never_turns_a_draft_into_a_send_to_somebody_he_did_not_name(gate, monkeypatch):
    from nucleo.flash import direct_action, ordered_send, payload_fill, undecided
    monkeypatch.setattr(direct_action, "completes", lambda *_a, **_k: "send_to")
    monkeypatch.setattr(undecided, "sure_order", lambda *_a: True)
    monkeypatch.setattr(payload_fill, "person_fill", lambda *_a: {})
    pay = {"contact": "Quinn", "text": "the numbers are in"}
    assert ordered_send.instead({}, "mensajeria", "draft", pay, "send the numbers to the team") is None
    assert ordered_send.instead({}, "mensajeria", "draft", pay, "send the numbers to quinn") == ("send_to", pay)


@pytest.fixture
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Paco Ruiz", "kind": "person", "email": "paco@example.com",
                                    "channels": [{"platform": "email", "handle": "paco@example.com"}],
                                    "preferred": "email"})
    return cd


def test_a_near_name_is_named_back_never_written_to(directory):
    from widgets.mensajeria import outbound
    t = outbound.resolve_target({"contact": "Pako Ruiz", "text": "hi", "channel": "email"})
    assert t["ok"] is False and t["near"] == ["Paco Ruiz"], t
    assert outbound.resolve_target({"contact": "paco ruiz", "text": "hi", "channel": "email"})["ok"] is True


def test_a_near_name_is_not_a_guest_either(directory):
    from widgets.agenda import invite
    g = invite.resolve_guests({"who": "Pako Ruiz"})
    assert g["emails"] == [] and g["ambiguous"] and g["ambiguous"][0][1] == ["Paco Ruiz"], g
    assert invite.resolve_guests({"who": "paco ruiz"})["emails"] == ["paco@example.com"]
