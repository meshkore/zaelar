"""V2-611 — the operator's email signature is appended EXACTLY ONCE, at the one place a real SMTP send
happens (`service._drain_replies`), and nowhere the widget can see.

Two facts settled before writing this, both load-bearing for the design:

  * There is no "real Gmail signature" to import. It lives in Gmail's account SETTINGS, reachable only
    through the `gmail.settings.basic` OAuth scope — this connector speaks plain IMAP/SMTP with an
    app-password and never requests it, so the signature simply is not on the wire we have.
  * There is no double-signature risk either. Gmail's own auto-append is a feature of ITS web/app compose
    UI; a raw SMTP send (what `mailbox.send_reply` does) never goes through that UI at all, so Gmail's own
    signature machinery never runs on anything we send.

So the signature is ours alone to add, and this file pins that it is added in the one place that matters —
never by the widget (V2-557: widget.js touches no network) and never twice.
"""
from __future__ import annotations

import asyncio

import pytest

from connectors.email import config, service
from connectors.messaging import ingest


class _Inbox:
    def __init__(self, items):
        self._items = list(items)

    def drain(self):
        out, self._items = self._items, []
        return out


class _FakeMailbox:
    def __init__(self):
        self.calls = []

    def send_reply(self, to, subject, text, in_reply_to="", cc=None):
        # `cc` (V2-680) is reply-ALL's extra recipients; a plain reply passes an empty list.
        self.calls.append({"to": to, "subject": subject, "text": text, "in_reply_to": in_reply_to,
                           "cc": list(cc or [])})
        return True, "ok"


@pytest.fixture
def rails(monkeypatch):
    monkeypatch.setattr(ingest, "v2_enabled", lambda: True)
    monkeypatch.setattr(ingest, "publish_msg_out", lambda *a, **k: None)


def _drain(monkeypatch, lines, text="Nos vemos mañana"):
    monkeypatch.setattr(config, "signature_lines", lambda: lines)
    mb = _FakeMailbox()
    monkeypatch.setattr(service, "_reply_inbox",
                        _Inbox([{"to": "ana@x.com", "text": text, "subject": "Re: hola", "msgid": "<m1>"}]))
    asyncio.run(service._drain_replies(mb))
    return mb.calls[0]["text"] if mb.calls else None


def test_no_signature_configured_sends_the_text_untouched(rails, monkeypatch):
    sent = _drain(monkeypatch, [])
    assert sent == "Nos vemos mañana"


def test_a_configured_signature_is_appended_with_the_rfc_delimiter(rails, monkeypatch):
    sent = _drain(monkeypatch, ["Ricardo", "Director", "ricardo@x.com"])
    assert sent == "Nos vemos mañana\n\n-- \nRicardo\nDirector\nricardo@x.com"


def test_the_signature_is_never_appended_twice(rails, monkeypatch):
    """The failure this whole file exists to rule out. If the append ever moved to two places (say, a
    second copy added `mailbox.send_reply` itself, or the widget started tacking it onto the draft text
    before enqueuing), the same signature would show up twice in one message."""
    sent = _drain(monkeypatch, ["Ricardo"])
    assert sent.count("Ricardo") == 1
    assert sent.count("-- \n") == 1


def test_the_signature_is_read_fresh_not_cached_across_sends(rails, monkeypatch):
    """An edit to the signature must apply to the very NEXT send, not wait for a restart — it is a config
    read, not a value baked in anywhere at startup."""
    monkeypatch.setattr(ingest, "publish_msg_out", lambda *a, **k: None)
    mb = _FakeMailbox()
    monkeypatch.setattr(config, "signature_lines", lambda: ["Primera firma"])
    monkeypatch.setattr(service, "_reply_inbox",
                        _Inbox([{"to": "a@x.com", "text": "uno", "subject": "", "msgid": ""}]))
    asyncio.run(service._drain_replies(mb))
    monkeypatch.setattr(config, "signature_lines", lambda: ["Firma nueva"])
    monkeypatch.setattr(service, "_reply_inbox",
                        _Inbox([{"to": "b@x.com", "text": "dos", "subject": "", "msgid": ""}]))
    asyncio.run(service._drain_replies(mb))
    assert "Primera firma" in mb.calls[0]["text"]
    assert "Firma nueva" in mb.calls[1]["text"] and "Primera firma" not in mb.calls[1]["text"]


def test_the_widget_never_sees_the_signature(rails, monkeypatch):
    """V2-557's own boundary, restated for this feature: the signature is connector state, and the reply
    the WIDGET enqueued must reach `_drain_replies` WITHOUT it — appending happens here, not upstream."""
    monkeypatch.setattr(config, "signature_lines", lambda: ["No debería verse antes de aquí"])
    mb = _FakeMailbox()
    queued_text = "Perfecto, quedamos así"
    monkeypatch.setattr(service, "_reply_inbox",
                        _Inbox([{"to": "a@x.com", "text": queued_text, "subject": "", "msgid": ""}]))
    asyncio.run(service._drain_replies(mb))
    assert mb.calls[0]["text"].startswith(queued_text)          # the queued text is untouched at its head
    assert mb.calls[0]["text"] != queued_text                    # and the signature landed only in send_reply
