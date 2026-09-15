"""V2-705 · the SEND door resolves a recipient reference even when the model decorates it.

Measured 2026-09-15, driving the meeting workflow by hand: the model called `send_to` with the recipient
as «Kryptonite (Telegram @cryptonitefund)» — the whole descriptive string, name plus its channel note —
and `directory.resolve` requires every word to appear in a contact's name, so «Kryptonite» was lost inside
its own annotation. The send failed «no tengo a … en el directorio» over a contact that was right there,
and the message never left. The name is the durable part of a recipient reference; the parenthetical, the
«, my friend from the fund», the trailing channel note are decoration. `_resolve_recipient` peels them.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Cryptonite", "kind": "person", "group": "work",
                                    "channels": [{"platform": "telegram", "handle": "@cryptonite_fund",
                                                  "chatId": "7477656357"}], "preferred": "telegram"})
    return cd


def _target(who, **extra):
    from widgets.mensajeria import outbound
    return outbound.resolve_target({"contact": who, "text": "hi", "channel": "telegram", **extra})


@pytest.mark.parametrize("who", [
    "Cryptonite",                                   # the plain name
    "Kryptonite",                                   # the operator's spelling (fuzzy, V2-698)
    "Kryptonite (Telegram @cryptonitefund)",        # THE measured failure: name + channel annotation
    "Cryptonite, my friend from the fund",          # name + a trailing clause
    "Cryptonite — the crypto contact",              # name + a dash note
])
def test_a_decorated_recipient_resolves_to_the_contacts_real_channel(directory, who):
    t = _target(who)
    assert t["ok"] is True, t
    assert t["name"] == "Cryptonite"
    assert t["to"] == "@cryptonite_fund" and t["chatId"] == "7477656357"


def test_the_whole_reference_still_wins_when_it_is_the_name(directory):
    """The cleaning is a FALLBACK: an exact/near name resolves on the first span, before any stripping."""
    assert _target("Cryptonite")["ok"] is True


def test_an_unknown_name_still_fails_clearly(directory):
    t = _target("Napoleon Bonaparte")
    assert t["ok"] is False and "directorio" in t["error"]


def test_two_matching_contacts_still_ask_which(tmp_path, monkeypatch):
    """Peeling decoration must not turn an ambiguity into a silent pick — writing to the wrong person is the
    one thing this door must never trade for (the refs.py doctrine)."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    for city in ("Madrid", "Sevilla"):
        cd.apply_action("add_contact", {"name": "Ana Garcia", "kind": "person", "group": "x", "city": city,
                                        "channels": [{"platform": "telegram", "handle": f"@ana_{city}"}]})
    t = _target("Ana Garcia (por Telegram)")
    assert t["ok"] is False and "PREGÚNTALE" in t["error"]


def test_a_bare_email_reference_is_untouched(directory):
    """An address said out loud is a complete way to reach somebody — the resolver must not mangle it."""
    from widgets.mensajeria import outbound
    t = outbound.resolve_target({"contact": "someone@example.com", "text": "hi", "channel": "email"})
    assert t["ok"] is True and t["platform"] == "email" and t["to"] == "someone@example.com"
