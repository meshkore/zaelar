"""V2-543 — email: attachments stop being skipped, and archive/delete reach the REAL mailbox.

BODY.PEEK[] always fetched the whole MIME message; `extract_text_body` explicitly skipped every attachment
part and the bytes were discarded. And the connector's only IMAP verbs were search/fetch/\\Seen — an
archive or delete asked in the widget had nowhere to go. The disposal tests drive `Mailbox._dispose`
against a fake IMAP object: folder discovery is RFC 6154 SPECIAL-USE first, and Gmail (which advertises
\\All and no \\Archive) archives by expunging from INBOX — label removal, its documented behavior.
"""
from __future__ import annotations

from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from connectors.email import mailbox


def _mail(attachments=()):
    m = MIMEMultipart()
    m["From"] = "Ana <a@b.com>"
    m["Subject"] = "foto"
    m["Date"] = "Mon, 01 Sep 2026 10:00:00 +0200"
    m.attach(MIMEText("mira esto", "plain", "utf-8"))
    for name, payload in attachments:
        img = MIMEImage(payload, _subtype="png")
        img.add_header("Content-Disposition", "attachment", filename=name)
        m.attach(img)
    return m


# ── Attachments ─────────────────────────────────────────────────────────────────────────────────────────────

def test_attachments_are_saved_and_the_message_carries_their_paths(tmp_path):
    parsed = mailbox.parse_message("7", _mail([("Foto de playa.png", b"\x89PNGfake")]).as_bytes(),
                                   media_dir=str(tmp_path))
    assert parsed["hasMedia"] and parsed["mediaType"] == "image"
    assert len(parsed["mediaUrls"]) == 1 and "eml_7_0_" in parsed["mediaUrls"][0]
    assert parsed["timestamp"] > 0
    assert (tmp_path / parsed["mediaUrls"][0].rsplit("/", 1)[-1]).is_file()


def test_without_a_media_dir_parsing_stays_byte_identical_to_before(tmp_path):
    parsed = mailbox.parse_message("7", _mail([("x.png", b"\x89PNG")]).as_bytes())
    assert "hasMedia" not in parsed and "mediaUrls" not in parsed


def test_an_oversized_attachment_is_skipped_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(mailbox, "MAX_ATTACHMENT_BYTES", 3)
    parsed = mailbox.parse_message("7", _mail([("big.png", b"\x89PNGtoolarge")]).as_bytes(),
                                   media_dir=str(tmp_path))
    assert "hasMedia" not in parsed, "too big: the mail still lands, text-only"


def test_the_body_walk_still_ignores_attachments_for_text():
    parsed = mailbox.parse_message("7", _mail([("x.png", b"\x89PNG")]).as_bytes())
    assert "mira esto" in parsed["body"] and "PNG" not in parsed["body"]


# ── Disposal against a fake IMAP ────────────────────────────────────────────────────────────────────────────

class _FakeImap:
    def __init__(self, folders, caps=("IMAP4REV1", "MOVE")):
        self._folders = folders
        self.capabilities = caps
        self.calls = []

    def list(self):
        return "OK", [line.encode() for line in self._folders]

    def select(self, box):
        self.calls.append(("select", box))
        return "OK", [b"1"]

    def uid(self, *args):
        self.calls.append(("uid",) + args)
        return "OK", [b""]

    def expunge(self):
        self.calls.append(("expunge",))
        return "OK", [b""]

    def logout(self):
        self.calls.append(("logout",))


def _mb(fake):
    mb = mailbox.Mailbox("a@b.com", "pw", "imap.x", 993, "smtp.x", 587)
    mb._imap = lambda: fake     # no network in a unit test, ever
    return mb


def test_archive_moves_to_the_special_use_archive_folder():
    fake = _FakeImap(['(\\HasNoChildren \\Archive) "/" "Archive"',
                      '(\\HasNoChildren \\Trash) "/" "Deleted Messages"'])
    ok, why = _mb(fake).archive(["10"])
    assert ok and "Archive" in why
    assert ("uid", "MOVE", "10", '"Archive"') in fake.calls


def test_gmail_archives_by_expunging_from_inbox_label_removal():
    fake = _FakeImap(['(\\HasNoChildren \\All) "/" "[Gmail]/Todos"',
                      '(\\HasNoChildren \\Trash) "/" "[Gmail]/Papelera"'])
    ok, why = _mb(fake).archive(["10"])
    assert ok
    assert not any(c[1] == "MOVE" for c in fake.calls if c[0] == "uid"), "Gmail: no MOVE — expunge IS archive"
    assert ("uid", "store", "10", "+FLAGS", "(\\Deleted)") in fake.calls
    assert ("expunge",) in fake.calls


def test_trash_moves_to_the_special_use_trash_folder():
    fake = _FakeImap(['(\\HasNoChildren \\Trash) "/" "[Gmail]/Papelera"'])
    ok, why = _mb(fake).trash(["10"])
    assert ok and "Papelera" in why
    assert ("uid", "MOVE", "10", '"[Gmail]/Papelera"') in fake.calls


def test_without_move_capability_trash_falls_back_to_copy_plus_deleted():
    fake = _FakeImap(['(\\HasNoChildren \\Trash) "/" "Trash"'], caps=("IMAP4REV1",))
    ok, _ = _mb(fake).trash(["10"])
    assert ok
    assert ("uid", "COPY", "10", '"Trash"') in fake.calls
    assert ("uid", "store", "10", "+FLAGS", "(\\Deleted)") in fake.calls


def test_a_mailbox_with_no_archive_anywhere_says_so_instead_of_deleting():
    """Refusing beats guessing: with no archive folder and no Gmail \\All, 'archive' must NOT quietly
    delete — that would turn a recoverable order into a destructive one."""
    fake = _FakeImap(['(\\HasNoChildren) "/" "INBOX"'])
    ok, why = _mb(fake).archive(["10"])
    assert ok is False and "archivo" in why
    assert not any(c[0] == "uid" for c in fake.calls), "nothing may be touched"
