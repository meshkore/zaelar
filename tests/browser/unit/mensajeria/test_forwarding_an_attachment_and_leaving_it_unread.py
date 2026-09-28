"""Forwarding what arrived, and leaving the original unread (operator, 2026-09-28).

The demo he asked for: open the unread Inworld AI receipt, take its invoice and send it to Andrew with a short
note («we're already trying Inworld, please book the invoice») — and at the end leave the original UNREAD, never
archived, because the same rehearsal runs again. None of it existed: `send_to` carried text only, the email
connector's first message was a «Re:» with no files, and nothing could put a mail back to unread.

No network anywhere below: the stores are isolated, SMTP and IMAP are doubles.
"""
from __future__ import annotations

import email
import os

import pytest


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    cd.apply_action("add_contact", {"name": "Andrew", "email": "andrew@example.com"})
    media = store.data_dir("mensajeria")
    os.makedirs(media, exist_ok=True)
    name = "eml_220440_0_Invoice-INW-263277.pdf"
    with open(os.path.join(media, name), "wb") as fh:
        fh.write(b"%PDF-1.4 invoice")
    db = md.load_db()
    db["items"] = [{"platform": "email", "chatId": "billing@inworld.ai", "messageId": "220440",
                    "senderId": "billing@inworld.ai", "from": "Inworld AI", "subject": "Your receipt",
                    "body": "Thanks", "media": [{"url": f"/widgets/mensajeria/asset/{name}", "type": "document",
                                                  "name": name}]}]
    store.save("mensajeria", db)
    return md


def test_the_invoice_of_the_message_on_the_list_travels_with_the_send(box):
    r = box.apply_action("send_to", {"contact": "Andrew", "channel": "email", "subject": "Inworld invoice",
                                     "text": "We're already testing Inworld — please book this invoice.",
                                     "attach_from": 1})
    assert r["ok"] and r["result"]["attachments"] == 1, r
    order = box.load_db()["pending_send"][0]
    assert order["to"] == "andrew@example.com"
    assert [os.path.basename(a) for a in order["attachments"]] == ["eml_220440_0_Invoice-INW-263277.pdf"]


def test_asked_for_and_absent_is_a_refusal_not_a_mail_without_its_file(box):
    r = box.apply_action("send_to", {"contact": "Andrew", "channel": "email", "text": "here", "attach_from": 9})
    assert r["ok"] is False and r["error"] == "no_attachment"
    assert not box.load_db().get("pending_send")


def test_the_original_goes_back_to_unread_in_his_app(box):
    r = box.apply_action("unread", {"n": 1})
    assert r["ok"], r
    assert box.load_db()["pending_unread"] == [{"platform": "email", "chatId": "billing@inworld.ai",
                                                 "messageId": "220440", "senderId": "billing@inworld.ai"}]


def test_the_connector_sends_a_new_mail_with_the_file_and_takes_seen_off(tmp_path, monkeypatch):
    from connectors.email import mailbox as mbx
    sent = []

    class _SMTP:
        def send_message(self, msg):
            sent.append(msg)

        def quit(self):
            pass

    mb = mbx.Mailbox.__new__(mbx.Mailbox)
    mb.address = "me@example.com"
    monkeypatch.setattr(mbx.Mailbox, "_connect_smtp", lambda self: _SMTP())
    monkeypatch.setattr(mbx.Mailbox, "_smtp_login", lambda self, s: None)
    pdf = tmp_path / "eml_220440_0_Invoice-INW-263277.pdf"
    pdf.write_bytes(b"%PDF-1.4 invoice")
    ok, _ = mb.send_message("andrew@example.com", "Inworld invoice", "please book it", [str(pdf)])
    assert ok
    msg = email.message_from_string(sent[0].as_string())
    assert msg["Subject"] == "Inworld invoice", "a forward is a NEW mail, never a «Re:»"
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["Invoice-INW-263277.pdf"]
    ok, why = mb.send_message("andrew@example.com", "x", "y", [str(tmp_path / "missing.pdf")])
    assert not ok and "adjunto" in why

    stored = []

    class _IMAP:
        def select(self, box):
            pass

        def uid(self, *a):
            stored.append(a)

        def logout(self):
            pass
    monkeypatch.setattr(mbx.Mailbox, "_imap", lambda self: _IMAP())
    assert mb.mark_unseen(["220440"])
    assert stored == [("store", "220440", "-FLAGS", "(\\Seen)")]


def test_the_owner_flushes_unread_orders_to_the_bus():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/mensajeria/owner.py").read_text("utf-8")
    assert "msgstore.take_pending_unread()" in src and "ingest.publish_mark_unread(key)" in src


def test_forward_is_one_name_for_a_send_with_the_files(box):
    """Measured 2026-09-28 (E block): for «send the invoice to andrew» the model reached for `reply` — to the
    SENDER — and the files never travelled. `forward` names what he asks: the message's files, to a person."""
    r = box.apply_action("forward", {"contact": "Andrew", "n": 1, "text": "Please book this invoice."})
    assert r["ok"] and r["result"]["attachments"] == 1, r
    order = box.load_db()["pending_send"][0]
    assert order["to"] == "andrew@example.com" and order["subject"] == "Fwd: Your receipt"
    assert order["attachments"]


def test_a_message_named_by_who_sent_it_is_found_in_its_thread_too(box):
    """Demo pass 2026-09-28: the model forwarded `n: 2`, a guess — the Inworld receipt was not on the visible list,
    and n 2 was somebody else's mail. Naming it («Inworld») finds it in the list or in the conversations kept."""
    from widgets import store
    db = box.load_db()
    item = db["items"].pop()
    db.setdefault("threads", {})["email|billing@inworld.ai"] = {"msgs": [{
        "id": "220440", "dir": "in", "who": "Inworld AI", "subject": "Your receipt", "ts": 1.0,
        "media": item["media"], "senderId": "billing@inworld.ai"}]}
    store.save("mensajeria", db)
    r = box.apply_action("forward", {"contact": "Andrew", "from": "inworld", "text": "Please book it."})
    assert r["ok"] and r["result"]["attachments"] == 1, r
    r2 = box.apply_action("unread", {"from": "Inworld"})
    assert r2["ok"] and box.load_db()["pending_unread"][0]["messageId"] == "220440"


def test_a_mail_from_his_own_address_is_his_echo_not_mail_for_him(monkeypatch):
    """Demo pass 2026-09-28 (full13 E3): the invoice forwarded to Andrew in an earlier run came back into INBOX
    from the operator's OWN address, sat first in his «for you» list, and the model took it for a mail from Andrew
    and asked which thread to send from — the send never happened."""
    from connectors.email import config as ecfg, mailbox as mbx
    monkeypatch.setattr(ecfg, "address", lambda: "Me@Example.com")
    raw = (b"From: Me <me@example.com>\r\nTo: andrew@example.com\r\nSubject: Fwd: Your receipt\r\n"
           b"Message-ID: <a@b>\r\n\r\nHi Andrew, forwarding the receipt.\r\n")
    assert mbx.parse_message("9", raw) is None
    other = raw.replace(b"From: Me <me@example.com>", b"From: Inworld AI <billing@inworld.ai>")
    assert (mbx.parse_message("10", other) or {}).get("senderId") == "billing@inworld.ai"


def test_the_mail_he_names_is_the_one_that_opens(box):
    """Demo pass 2026-09-28 (full13 E2): «open it» after «did inworld send me something?» reached
    `open` with `item: "Inworld AI"` and an EMPTY payload — `open` never said which key names a chat, so the
    reference fell on the floor and the card showed the list instead of the receipt."""
    from widgets import refs
    res = refs.resolve("mensajeria", "open", "Inworld AI", {})
    assert res.ok and res.payload == {"name": "Inworld AI"}, res
    assert refs.resolve("mensajeria", "unread", "Inworld", {}).payload == {"from": "Inworld"}
    r = box.apply_action("open", res.payload)
    assert r.get("ok") is not False, r


def test_open_it_after_talking_about_one_mail_is_declared_that_mail():
    """Demo pass 2026-09-28 (full14 E2): «open it», right after «Inworld AI sent you a receipt», reached
    `show_view {platform: email}` — the inbox, not the receipt. The only text the model reads about `open` never
    said that «it» after one mail is that mail."""
    import json
    from pathlib import Path
    m = json.loads((Path(__file__).resolve().parents[4] / "widgets/mensajeria/manifest.json").read_text("utf-8"))
    assert "open it" in m["actions"]["open"]["desc"] and "no la bandeja" in m["actions"]["open"]["desc"]


def test_a_message_named_in_the_payload_is_not_a_loose_pronoun(monkeypatch):
    """Demo pass 2026-09-28 (full16 E2): «open it» right after the Inworld receipt was talked about — the model
    called `open {name: "Inworld AI"}` with an empty `item`, the card was not on screen, and the guard against a
    loose pronoun on an absent card escalated it instead of opening the mail. The name in the payload IS the
    anchor; a truly empty call on an absent card still escalates."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"open_widgets": []})
    from nucleo.flash import frontend as fe
    assert not fe.absent_widget_misroute("mensajeria", "open", "", payload={"name": "Inworld AI"})
    assert fe.absent_widget_misroute("mensajeria", "open", "", payload={})
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    assert "named_widget=_identify(text), payload=payload)" in (
        root / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "payload=_wd[\"args\"].get(\"payload\")" in (root / "nucleo/flash/probe.py").read_text("utf-8")
    m = __import__("json").loads((root / "widgets/mensajeria/manifest.json").read_text("utf-8"))["actions"]
    assert "NO es esto" in m["dismiss"]["desc"], "«leave it unread» belongs to unread, not to dismiss"
