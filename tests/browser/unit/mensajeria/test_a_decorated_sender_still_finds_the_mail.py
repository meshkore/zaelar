"""A forward names its mail with decoration — «Vendor AI (recibo #2281-4878)» — and still finds it (demo pass 107).

E3: `forward {from: "Inworld AI (recibo #2281-4878)"}` was refused «the message he pointed at is not on the card
with its attachments» — the archive was asked by that whole string, as a sender and as free text, and neither
matched. Passes before had sent «Inworld» or the plain subject and it went. The core of what he named — without
the parenthesis and the receipt number — is asked too.
"""
from __future__ import annotations


def test_the_core_of_a_decorated_sender_is_asked(monkeypatch):
    from connectors.messaging import archive
    from widgets.mensajeria import outbound
    asked = []

    def search(q=None, sender=None, **_kw):
        asked.append(sender or q)
        return [{"chat_id": "mail:inbox", "msg_id": "42"}] if (sender or q) == "Vendor AI" else []
    monkeypatch.setattr(archive, "search", search)
    assert outbound._mail_identities(None, {"from": "Vendor AI (recibo #2281-4878)"}) == [("mail:inbox", "42")], asked


def test_a_plain_sender_is_asked_once(monkeypatch):
    from connectors.messaging import archive
    from widgets.mensajeria import outbound
    asked = []
    monkeypatch.setattr(archive, "search", lambda q=None, sender=None, **_kw: asked.append(sender or q) or [])
    outbound._mail_identities(None, {"from": "Vendor AI"})
    assert asked == ["Vendor AI", "Vendor AI"], asked
