"""Forwarding what arrived, and leaving the original unread (operator, 2026-09-28).

The demo he asked for: open the unread Acme Cloud receipt, take its invoice and send it to Quinn with a short
note («we're already trying Acme, please book the invoice») — and at the end leave the original UNREAD, never
archived, because the same rehearsal runs again. None of it existed: `send_to` carried text only, the email
connector's first message was a «Re:» with no files, and nothing could put a mail back to unread.

No network anywhere below: the stores are isolated, SMTP and IMAP are doubles.
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

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
    cd.apply_action("add_contact", {"name": "Quinn", "email": "quinn@example.com"})
    media = store.data_dir("mensajeria")
    os.makedirs(media, exist_ok=True)
    name = "eml_100001_0_Invoice-ACM-100001.pdf"
    with open(os.path.join(media, name), "wb") as fh:
        fh.write(b"%PDF-1.4 invoice")
    db = md.load_db()
    db["items"] = [{"platform": "email", "chatId": "billing@acme-cloud.example", "messageId": "100001",
                    "senderId": "billing@acme-cloud.example", "from": "Acme Cloud", "subject": "Your receipt",
                    "body": "Thanks", "media": [{"url": f"/widgets/mensajeria/asset/{name}", "type": "document",
                                                  "name": name}]}]
    store.save("mensajeria", db)
    return md


def test_the_invoice_of_the_message_on_the_list_travels_with_the_send(box):
    r = box.apply_action("send_to", {"contact": "Quinn", "channel": "email", "subject": "Acme invoice",
                                     "text": "We're already testing Acme — please book this invoice.",
                                     "attach_from": 1})
    assert r["ok"] and r["result"]["attachments"] == 1, r
    order = box.load_db()["pending_send"][0]
    assert order["to"] == "quinn@example.com"
    assert [os.path.basename(a) for a in order["attachments"]] == ["eml_100001_0_Invoice-ACM-100001.pdf"]


def test_asked_for_and_absent_is_a_refusal_not_a_mail_without_its_file(box):
    r = box.apply_action("send_to", {"contact": "Quinn", "channel": "email", "text": "here", "attach_from": 9})
    assert r["ok"] is False and r["error"] == "no_attachment"
    assert not box.load_db().get("pending_send")


def test_the_original_goes_back_to_unread_in_his_app(box):
    r = box.apply_action("unread", {"n": 1})
    assert r["ok"], r
    assert box.load_db()["pending_unread"] == [{"platform": "email", "chatId": "billing@acme-cloud.example",
                                                 "messageId": "100001", "senderId": "billing@acme-cloud.example"}]


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
    pdf = tmp_path / "eml_100001_0_Invoice-ACM-100001.pdf"
    pdf.write_bytes(b"%PDF-1.4 invoice")
    ok, _ = mb.send_message("quinn@example.com", "Acme invoice", "please book it", [str(pdf)])
    assert ok
    msg = email.message_from_string(sent[0].as_string())
    assert msg["Subject"] == "Acme invoice", "a forward is a NEW mail, never a «Re:»"
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["Invoice-ACM-100001.pdf"]
    ok, why = mb.send_message("quinn@example.com", "x", "y", [str(tmp_path / "missing.pdf")])
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
    assert mb.mark_unseen(["100001"])
    assert stored == [("store", "100001", "-FLAGS", "(\\Seen)")]


def test_the_owner_flushes_unread_orders_to_the_bus():
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "widgets/mensajeria/owner.py").read_text("utf-8")
    assert "msgstore.take_pending_unread()" in src and "ingest.publish_mark_unread(key)" in src


def test_forward_is_one_name_for_a_send_with_the_files(box):
    """Measured 2026-09-28 (E block): for «send the invoice to quinn» the model reached for `reply` — to the
    SENDER — and the files never travelled. `forward` names what he asks: the message's files, to a person."""
    r = box.apply_action("forward", {"contact": "Quinn", "n": 1, "text": "Please book this invoice."})
    assert r["ok"] and r["result"]["attachments"] == 1, r
    order = box.load_db()["pending_send"][0]
    assert order["to"] == "quinn@example.com" and order["subject"] == "Fwd: Your receipt"
    assert order["attachments"]


def test_a_message_named_by_who_sent_it_is_found_in_its_thread_too(box):
    """Demo pass 2026-09-28: the model forwarded `n: 2`, a guess — the Acme invoice was not on the visible list,
    and n 2 was somebody else's mail. Naming it («Acme») finds it in the list or in the conversations kept."""
    from widgets import store
    db = box.load_db()
    item = db["items"].pop()
    db.setdefault("threads", {})["email|billing@acme-cloud.example"] = {"msgs": [{
        "id": "100001", "dir": "in", "who": "Acme Cloud", "subject": "Your receipt", "ts": 1.0,
        "media": item["media"], "senderId": "billing@acme-cloud.example"}]}
    store.save("mensajeria", db)
    r = box.apply_action("forward", {"contact": "Quinn", "from": "acme", "text": "Please book it."})
    assert r["ok"] and r["result"]["attachments"] == 1, r
    r2 = box.apply_action("unread", {"from": "Acme"})
    assert r2["ok"] and box.load_db()["pending_unread"][0]["messageId"] == "100001"


def test_a_mail_from_his_own_address_is_his_echo_not_mail_for_him(monkeypatch):
    """Demo pass 2026-09-28 (full13 E3): the invoice forwarded to Quinn in an earlier run came back into INBOX
    from the operator's OWN address, sat first in his «for you» list, and the model took it for a mail from Quinn
    and asked which thread to send from — the send never happened."""
    from connectors.email import config as ecfg, mailbox as mbx
    monkeypatch.setattr(ecfg, "address", lambda: "Me@Example.com")
    raw = (b"From: Me <me@example.com>\r\nTo: quinn@example.com\r\nSubject: Fwd: Your receipt\r\n"
           b"Message-ID: <a@b>\r\n\r\nHi Quinn, forwarding the receipt.\r\n")
    assert mbx.parse_message("9", raw) is None
    other = raw.replace(b"From: Me <me@example.com>", b"From: Acme Cloud <billing@acme-cloud.example>")
    assert (mbx.parse_message("10", other) or {}).get("senderId") == "billing@acme-cloud.example"


def test_the_mail_he_names_is_the_one_that_opens(box):
    """Demo pass 2026-09-28 (full13 E2): «open it» after «did acme send me something?» reached
    `open` with `item: "Acme Cloud"` and an EMPTY payload — `open` never said which key names a chat, so the
    reference fell on the floor and the card showed the list instead of the receipt."""
    from widgets import refs
    res = refs.resolve("mensajeria", "open", "Acme Cloud", {})
    assert res.ok and res.payload == {"name": "Acme Cloud"}, res
    assert refs.resolve("mensajeria", "unread", "Acme", {}).payload == {"from": "Acme"}
    r = box.apply_action("open", res.payload)
    assert r.get("ok") is not False, r


def test_open_it_after_talking_about_one_mail_is_declared_that_mail():
    """Demo pass 2026-09-28 (full14 E2): «open it», right after «Acme Cloud sent you a receipt», reached
    `show_view {platform: email}` — the inbox, not the receipt. The only text the model reads about `open` never
    said that «it» after one mail is that mail."""
    import json
    from pathlib import Path
    m = json.loads((Path(__file__).resolve().parents[4] / "widgets/mensajeria/manifest.json").read_text("utf-8"))
    assert "open it" in m["actions"]["open"]["desc"] and "no la bandeja" in m["actions"]["open"]["desc"]


def test_a_message_named_in_the_payload_is_not_a_loose_pronoun(monkeypatch):
    """Demo pass 2026-09-28 (full16 E2): «open it» right after the Acme invoice was talked about — the model
    called `open {name: "Acme Cloud"}` with an empty `item`, the card was not on screen, and the guard against a
    loose pronoun on an absent card escalated it instead of opening the mail. The name in the payload IS the
    anchor; a truly empty call on an absent card still escalates."""
    from memory import api as _mem
    monkeypatch.setattr(_mem, "state", lambda: {"open_widgets": []})
    from nucleo.flash import frontend as fe
    assert not fe.absent_widget_misroute("mensajeria", "open", "", payload={"name": "Acme Cloud"})
    assert fe.absent_widget_misroute("mensajeria", "open", "", payload={})
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    assert "named_widget=_identify(text), payload=payload)" in _vts.read(root / "voice/engine/llm/providers/nucleo.py")
    m = __import__("json").loads((root / "widgets/mensajeria/manifest.json").read_text("utf-8"))["actions"]
    assert "NO es esto" in m["dismiss"]["desc"], "«leave it unread» belongs to unread, not to dismiss"


# ── demo pass 37 (2026-09-29), E3: the refusal reaches the turn ──────────────────────────────────────────────────
# `forward {n: 1}` pointed at a message with no files; the owner refused it `no_attachment` out of sight and the
# turn went on as if the invoice had gone to Quinn. The pre-check that runs BEFORE the order is queued says it.

def test_a_forward_of_a_message_without_files_is_refused_before_it_is_queued(box):
    db = box.load_db()
    db["items"].insert(0, {"platform": "email", "chatId": "ago@x.invalid", "messageId": "999",
                           "senderId": "ago@x.invalid", "from": "Quinn", "subject": "Re: invoice", "body": "ok"})
    from widgets import store
    store.save("mensajeria", db)
    r = box.answer_action("forward", {"n": 1, "contact": "Quinn", "text": "please book it"})
    assert r and r["ok"] is False and "adjuntos" in r["error"], r
    assert "NUNCA reenvíes el mensaje de otro remitente" in r["error"], "the refusal invites a stand-in sender"


def test_a_forward_of_the_message_with_the_invoice_passes_the_pre_check(box):
    r = box.answer_action("forward", {"from": "Acme Cloud", "contact": "Quinn", "text": "please book it"})
    assert r and r["ok"], r


# ── demo pass 52 (2026-09-29), E3: a description, a `note`, and the stand-in it led to ─────────────────────────
# The model sent `forward {to, note}` with the mail in `item`: «Acme invoice email from September 27, 2026». `note`
# was not read as the text, and the description matched no sender as one string, so the same-turn correction guessed
# `from: Soporte de HostCo`. `note` is the text, `item` lands in `from`, and a description finds the message that
# carries most of its words.

def test_a_description_finds_the_message_it_describes(box):
    from widgets import store
    db = box.load_db()
    db["items"].insert(0, {"platform": "email", "chatId": "support@hosting.example", "messageId": "501",
                           "senderId": "support@hosting.example", "from": "Soporte de HostCo",
                           "subject": "Your invoice is available", "body": "x"})
    store.save("mensajeria", db)
    from widgets.mensajeria import outbound
    hit = outbound._message_ref(box.load_db(), {"from": "the receipt email from Acme of September 27, 2026"})
    assert hit and hit["messageId"] == "100001", hit


def test_note_is_the_text_and_item_is_the_from():
    from widgets import contract, refs
    assert contract.fold_aliases("mensajeria", "forward", {"contact": "Quinn", "note": "book it"})["text"] == "book it"
    assert refs.id_field_for_action("mensajeria", "forward") == "from"


def test_a_description_finds_a_mail_that_only_lives_in_its_thread(box):
    """Demo pass 53, E3: the receipt came back from the history into its THREAD, not the visible list, and
    «Acme Cloud receipt invoice1000-0001» was scored against the list only — nothing matched, nothing was sent."""
    from widgets import store
    db = box.load_db()
    item = db["items"].pop()
    db["items"] = [{"platform": "email", "chatId": "support@hosting.example", "messageId": "501", "from": "Soporte de HostCo",
                    "subject": "Your invoice is available", "body": "x"}]
    db.setdefault("threads", {})["email|billing@acme-cloud.example"] = {"msgs": [
        {"id": "100001", "dir": "in", "who": "Acme Cloud", "ts": 1.0,
         "body": "[Asunto: Your receipt from Acme Cloud #1000-0001] Thanks", "media": item["media"]}]}
    store.save("mensajeria", db)
    from widgets.mensajeria import outbound
    hit = outbound._message_ref(box.load_db(), {"from": "Acme Cloud receipt invoice1000-0001"})
    assert hit and hit["messageId"] == "100001", hit


# ── demo passes 38-53 (2026-09-29), E3: the mail on the card came WITHOUT its files ──────────────────────────────
# Six passes ended «el mensaje que él señaló no está en la tarjeta con sus adjuntos todavía»: the receipt had been
# brought back from the archive (a row, no bytes) and the forward's pre-check found nothing on disk. The archive
# keeps the mailbox UID, so the files are ONE read-only IMAP fetch away — done in the turn, never a refusal that
# sends the operator to «open it» again.

class _Mailbox:
    def __init__(self, log):
        self.log = log

    def fetch_older(self, address, before_uid, limit=30, media_dir=None):
        self.log.append((address, before_uid, limit))
        path = os.path.join(media_dir, "eml_100001_0_Invoice-ACM-100001.pdf")
        with open(path, "wb") as fh:
            fh.write(b"%PDF-1.4 invoice")
        return [{"messageId": "100001", "subject": "Your receipt", "mediaUrls": [path]}], True


def test_a_mail_on_the_card_without_its_files_gets_them_from_the_mailbox_in_the_turn(box, monkeypatch):
    from widgets import store
    from widgets.mensajeria import outbound
    db = box.load_db()
    db["items"] = []
    db.setdefault("threads", {})["email|billing@acme-cloud.example"] = {"msgs": [
        {"id": "100001", "dir": "in", "who": "Acme Cloud", "ts": 1.0, "subject": "Your receipt",
         "body": "Your receipt from Acme Cloud\nThanks"}]}
    store.save("mensajeria", db)
    os.remove(os.path.join(store.data_dir("mensajeria"), "eml_100001_0_Invoice-ACM-100001.pdf"))
    asked = []
    from connectors.email import config as ecfg
    monkeypatch.setattr(ecfg, "mailbox", lambda: _Mailbox(asked))
    outbound._MAILBOX_FILES.clear()
    r = box.answer_action("forward", {"from": "Acme Cloud", "contact": "Quinn", "text": "please book it"})
    assert r and r["ok"], r
    r2 = box.apply_action("forward", {"from": "Acme Cloud", "contact": "Quinn", "text": "please book it"})
    assert r2["ok"] and r2["result"]["attachments"] == 1, r2
    order = box.load_db()["pending_send"][0]
    assert [os.path.basename(a) for a in order["attachments"]] == ["eml_100001_0_Invoice-ACM-100001.pdf"]
    assert asked == [("billing@acme-cloud.example", "100002", 1)], "one fetch by the mail's own UID; the send reuses it"


def test_a_mail_only_the_archive_knows_is_fetched_by_its_archived_uid(box, monkeypatch):
    """Nothing on the card at all (a reset, or a list that scrolled past it): the archive row names the chat and the
    UID, and that is enough to bring the files — without a stand-in sender."""
    from widgets import store
    from widgets.mensajeria import outbound
    from connectors.messaging import archive
    db = box.load_db()
    db["items"] = [{"platform": "email", "chatId": "support@hosting.example", "messageId": "501", "from": "Soporte de HostCo",
                    "subject": "Your invoice is available", "body": "x"}]
    db["threads"] = {}
    store.save("mensajeria", db)
    os.remove(os.path.join(store.data_dir("mensajeria"), "eml_100001_0_Invoice-ACM-100001.pdf"))
    archive.record("email", "billing@acme-cloud.example", [{"messageId": "100001", "body": "Your receipt from Acme Cloud",
                                                      "ts": 1.0, "from": "Acme Cloud"}], direction="in",
                   chat_name="Acme Cloud")
    asked = []
    from connectors.email import config as ecfg
    monkeypatch.setattr(ecfg, "mailbox", lambda: _Mailbox(asked))
    outbound._MAILBOX_FILES.clear()
    r = box.answer_action("forward", {"from": "Acme Cloud", "contact": "Quinn", "text": "please book it"})
    assert r and r["ok"], r
    assert asked == [("billing@acme-cloud.example", "100002", 1)]


def test_two_contacts_with_one_address_are_one_recipient(box):
    """Demo pass 54 (2026-09-29), E3: the same-turn correction retried with the ADDRESS, and the directory held two
    contacts with it — «tengo 2 contactos que encajan con contact@example.com». Two names for one mailbox are one
    recipient; asking which costs the turn and changes nothing about where the mail goes."""
    from widgets.contactos import data as cd
    from widgets.mensajeria import outbound
    cd.apply_action("add_contact", {"name": "Andrés Garcia", "email": "quinn@example.com"})
    t = outbound.resolve_target({"contact": "quinn@example.com", "channel": "email", "text": "book it"})
    assert t["ok"] and t["to"] == "quinn@example.com", t


# ── demo passes 122-124 (2026-10-06 → 10-14), E3: a description in another language than the mail ────────────────
# E2 opened the Acme conversation, and E3's forward described the mail as «el recibo de Acme». Only one of its
# words is in the (English) mail, so the description found nothing — and a `from` that finds nothing never looked at
# the conversation that was OPEN, which is what «this one» means. Three passes in a row refused the forward. The open
# conversation answers only when it is the sender he described: never a stand-in.

def _open_acme(box, active_chat):
    from widgets import store
    db = box.load_db()
    item = db["items"].pop()
    db["items"] = [{"platform": "email", "chatId": "support@hosting.example", "messageId": "501", "from": "Soporte de HostCo",
                    "subject": "Your invoice is available", "body": "x"}]
    db.setdefault("threads", {})["email|billing@example.invalid"] = {"msgs": [
        {"id": "100001", "dir": "in", "who": "Acme Cloud", "ts": 1.0,
         "body": "[Asunto: Your receipt from Acme Cloud #1000-0001] Thanks", "media": item["media"]}]}
    db.setdefault("threads", {})["email|support@hosting.example"] = {"msgs": [
        {"id": "501", "dir": "in", "who": "Soporte de HostCo", "ts": 2.0, "body": "Your invoice is available"}]}
    db["active_chat"] = active_chat
    store.save("mensajeria", db)


def test_a_description_that_finds_nothing_falls_to_the_open_conversation_of_that_sender(box):
    from widgets.mensajeria import outbound
    _open_acme(box, {"platform": "email", "chatId": "billing@example.invalid"})
    hit = outbound._message_ref(box.load_db(), {"from": "el recibo de Acme"})
    assert hit and hit["messageId"] == "100001", hit
    r = box.answer_action("forward", {"from": "el recibo de Acme", "contact": "Quinn", "text": "please book it"})
    assert r and r["ok"], r


def test_the_open_conversation_of_another_sender_is_never_the_stand_in(box):
    from widgets.mensajeria import outbound
    _open_acme(box, {"platform": "email", "chatId": "support@hosting.example", "name": "Soporte de HostCo"})
    assert outbound._message_ref(box.load_db(), {"from": "el recibo de Acme"}) is None


# ── demo pass 127 (2026-10-14), E3: the receipt went to Quinn TWICE ─────────────────────────────────────────────
# The verdict turned the model's `send_to` into a forward that went out; the model's own forward (refused for a
# missing text) was then corrected in the same turn and went out too. The same files to the same person a moment
# later are one send, whichever path sends them again.

def test_the_same_files_to_the_same_person_go_out_once(box):
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Rowan", "email": "rowan@example.com"})
    first = box.apply_action("forward", {"from": "Acme Cloud", "contact": "Quinn", "text": "please book it"})
    again = box.apply_action("forward", {"from": "Acme Cloud", "contact": "Quinn", "text": "We're trying it — book it."})
    other = box.apply_action("forward", {"from": "Acme Cloud", "contact": "Rowan", "text": "fyi"})
    assert first["ok"] and again["ok"] and other["ok"], (first, again, other)
    assert again["result"].get("already_sent") and not other["result"].get("already_sent")
    assert [o["to"] for o in box.load_db()["pending_send"]] == ["quinn@example.com", "rowan@example.com"]


def test_two_messages_without_files_are_two_sends(box):
    box.apply_action("send_to", {"contact": "Quinn", "channel": "email", "text": "one"})
    box.apply_action("send_to", {"contact": "Quinn", "channel": "email", "text": "two"})
    assert [o["text"] for o in box.load_db()["pending_send"]] == ["one", "two"]
