"""V2-680 — the server half: one draft per CONVERSATION, and a reply-all that really copies somebody.

Before this the widget held exactly ONE draft, so starting a reply to a second conversation destroyed the
first without a word. And `reply_all` could not have existed at all: the stored email item carried only its
sender, so a reply-all would have sent the identical single reply under a second name — which is a worse
failure than not offering the choice, because the operator would believe the other recipients were
answered. The recipients are captured where they are visible (the connector's own parse) and travel
draft → queue → SMTP Cc.
"""
from __future__ import annotations

import email as email_lib

import pytest

from connectors.email import mailbox
from widgets import store as wstore
from widgets.mensajeria import data, drafts as mdrafts


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    """A unit test never touches the operator's real widget store (the standing rule, and the failure this
    repo has already paid for twice)."""
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    yield


def _mail(mid: str, sender: str, recipients=None) -> dict:
    it = {"platform": "email", "chatId": sender, "senderId": sender, "messageId": mid,
          "from": sender, "subject": "Asunto", "msgid": f"<{mid}@x>", "body": "cuerpo",
          "urgencia": "media", "dirigido_a_mi": True, "ts": 1700000000}
    if recipients is not None:
        it["recipients"] = recipients
    return it


def _seed(*items):
    db = data.load_db()
    db["items"] = list(items)
    wstore.save(data.WIDGET_ID, db)


# ── one draft per conversation ────────────────────────────────────────────────────────────────────────

def test_two_conversations_keep_two_separate_drafts():
    """Two mails from the SAME sender on purpose: that is the ordinary case (a thread), and it is the one
    a key built from the conversation alone cannot separate. Two different senders would pass under a key
    that ignored the message entirely, which is exactly what the disarm caught."""
    _seed(_mail("uid-a", "ana@x.com"), _mail("uid-b", "ana@x.com"))
    data.apply_action("draft", {"messageId": "uid-a", "text": "Sobre lo primero"})
    data.apply_action("draft", {"messageId": "uid-b", "text": "Sobre lo segundo"})
    drafts = data.view_data()["drafts"]
    assert {d["text"] for d in drafts.values()} == {"Sobre lo primero", "Sobre lo segundo"}


def test_sending_one_draft_leaves_the_others_alone():
    _seed(_mail("uid-a", "ana@x.com"), _mail("uid-b", "luis@x.com"))
    data.apply_action("draft", {"messageId": "uid-a", "text": "Para Ana"})
    data.apply_action("draft", {"messageId": "uid-b", "text": "Para Luis"})
    data.apply_action("send_draft", {"messageId": "uid-a"})
    left = data.view_data()["drafts"]
    assert [d["text"] for d in left.values()] == ["Para Luis"]


def test_clearing_a_draft_clears_only_that_one():
    _seed(_mail("uid-a", "ana@x.com"), _mail("uid-b", "luis@x.com"))
    data.apply_action("draft", {"messageId": "uid-a", "text": "Para Ana"})
    data.apply_action("draft", {"messageId": "uid-b", "text": "Para Luis"})
    data.apply_action("draft", {"messageId": "uid-a", "text": "   "})
    left = data.view_data()["drafts"]
    assert [d["text"] for d in left.values()] == ["Para Luis"]


def test_a_bare_send_still_means_the_last_one_he_touched():
    """A voice «envíalo» names no conversation, and it meant the one just dictated before drafts were per
    conversation. That has to keep working, or the voice path regresses to please the widget."""
    _seed(_mail("uid-a", "ana@x.com"), _mail("uid-b", "luis@x.com"))
    data.apply_action("draft", {"messageId": "uid-a", "text": "Para Ana"})
    data.apply_action("draft", {"messageId": "uid-b", "text": "Para Luis"})
    out = data.apply_action("send_draft", {})
    assert out["ok"] and out["text"] == "Para Luis"


def test_a_draft_is_never_keyed_on_the_POSITIONAL_number():
    """`n` is reassigned on every save (`_renumber`), so keying on it would hand one conversation's
    half-written reply to whatever message inherited that number next."""
    _seed(_mail("uid-a", "ana@x.com"), _mail("uid-b", "luis@x.com"))
    data.apply_action("draft", {"n": 1, "text": "Para el primero"})
    key = next(iter(data.view_data()["drafts"]))
    assert key == "m:uid-a", key            # addressed by identity, not by position


def test_a_reset_keeps_what_he_wrote_himself():
    """A reset clears what ARRIVED. An unsent reply is the operator's own writing and is not ours to
    throw away — the same reasoning that already preserves his autoresponder and his lens criteria."""
    _seed(_mail("uid-a", "ana@x.com"))
    data.apply_action("draft", {"messageId": "uid-a", "text": "A medio escribir"})
    fresh = data.blank()
    assert [d["text"] for d in (fresh.get("drafts") or {}).values()] == ["A medio escribir"]
    assert fresh["items"] == []             # and it really did clear what arrived


def test_the_store_of_drafts_is_bounded():
    """The cap exists so the store cannot grow without limit. Nothing expires on a clock: deleting an
    unfinished reply because a week passed would lose something he never asked us to throw away."""
    _seed(*[_mail(f"uid-{i}", f"p{i}@x.com") for i in range(mdrafts.MAX + 10)])
    for i in range(mdrafts.MAX + 10):
        data.apply_action("draft", {"messageId": f"uid-{i}", "text": f"t{i}"})
    drafts = data.view_data()["drafts"]
    assert len(drafts) == mdrafts.MAX
    assert "m:uid-0" not in drafts and f"m:uid-{mdrafts.MAX + 9}" in drafts   # oldest out, newest in


# ── reply-all ─────────────────────────────────────────────────────────────────────────────────────────

def _queued(db):
    return db.get("pending_reply") or []


def test_a_reply_all_really_copies_the_other_recipients():
    _seed(_mail("uid-a", "ana@x.com", recipients=["marta@x.com", "pedro@x.com"]))
    data.apply_action("draft", {"messageId": "uid-a", "text": "A todos", "reply_all": True})
    data.apply_action("send_draft", {"messageId": "uid-a"})
    q = _queued(data.load_db())
    assert q and q[-1]["cc"] == ["marta@x.com", "pedro@x.com"], q


def test_a_plain_reply_copies_nobody():
    """The default, and the counterweight: copying people the operator did not choose to copy is the
    worse direction of this mistake."""
    _seed(_mail("uid-a", "ana@x.com", recipients=["marta@x.com"]))
    data.apply_action("draft", {"messageId": "uid-a", "text": "Solo a ti"})
    data.apply_action("send_draft", {"messageId": "uid-a"})
    q = _queued(data.load_db())
    assert q and q[-1]["cc"] == [], q


def test_reply_all_on_a_mail_with_nobody_else_copies_nobody():
    """An item ingested before this field existed carries no recipients at all. The honest result is a
    plain reply, never an invented list."""
    _seed(_mail("uid-a", "ana@x.com"))
    data.apply_action("draft", {"messageId": "uid-a", "text": "A todos", "reply_all": True})
    data.apply_action("send_draft", {"messageId": "uid-a"})
    q = _queued(data.load_db())
    assert q and q[-1]["cc"] == [], q


# ── where the recipients come from ────────────────────────────────────────────────────────────────────

def test_reply_all_never_copies_our_own_address_or_the_sender(monkeypatch):
    """Copying ourselves on our own outgoing mail is a bug every real client avoids, and the sender is
    already the To — listing them again would duplicate the recipient."""
    from connectors.email import config as ecfg
    monkeypatch.setattr(ecfg, "address", lambda: "yo@x.com")
    msg = email_lib.message_from_string(
        "From: Ana <ana@x.com>\r\n"
        "To: yo@x.com, Marta <marta@x.com>\r\n"
        "Cc: ana@x.com, Pedro <pedro@x.com>\r\n"
        "Subject: hola\r\n\r\ncuerpo\r\n")
    assert mailbox._other_recipients(msg, "ana@x.com") == ["marta@x.com", "pedro@x.com"]


def test_a_repeated_recipient_is_listed_once(monkeypatch):
    from connectors.email import config as ecfg
    monkeypatch.setattr(ecfg, "address", lambda: "yo@x.com")
    msg = email_lib.message_from_string(
        "From: ana@x.com\r\nTo: Marta <marta@x.com>\r\nCc: MARTA@x.com\r\n\r\nx\r\n")
    assert mailbox._other_recipients(msg, "ana@x.com") == ["marta@x.com"]


def test_a_mail_addressed_only_to_us_has_no_reply_all(monkeypatch):
    from connectors.email import config as ecfg
    monkeypatch.setattr(ecfg, "address", lambda: "yo@x.com")
    msg = email_lib.message_from_string("From: ana@x.com\r\nTo: yo@x.com\r\n\r\nx\r\n")
    assert mailbox._other_recipients(msg, "ana@x.com") == []


def test_the_cc_header_is_what_the_recipients_SEE():
    """`send_message` derives the envelope from To+Cc on its own, so the header is the whole mechanism —
    there is no second list to keep in sync. Checked on the composed message, not on the send."""
    sent = {}
    # Compose through the real method with the transport stubbed at its own seam.
    mb = mailbox.Mailbox.__new__(mailbox.Mailbox)
    mb.address = "yo@x.com"
    mb._connect_smtp = lambda: _FakeSMTP(sent)
    mb._smtp_login = lambda s: None
    ok, _info = mb.send_reply("ana@x.com", "Asunto", "cuerpo", "", ["marta@x.com", "pedro@x.com"])
    assert ok
    assert sent["msg"]["To"] == "ana@x.com"
    assert sent["msg"]["Cc"] == "marta@x.com, pedro@x.com"


def test_a_plain_send_carries_NO_cc_header():
    sent = {}
    mb = mailbox.Mailbox.__new__(mailbox.Mailbox)
    mb.address = "yo@x.com"
    mb._connect_smtp = lambda: _FakeSMTP(sent)
    mb._smtp_login = lambda s: None
    ok, _info = mb.send_reply("ana@x.com", "Asunto", "cuerpo")
    assert ok and sent["msg"]["Cc"] is None


class _FakeSMTP:
    def __init__(self, sink):
        self.sink = sink

    def send_message(self, msg):
        self.sink["msg"] = msg

    def quit(self):
        pass

    def close(self):
        pass
