"""A mail the archive never indexed is asked of the real mailbox, and indexed on the way back (demo pass 30, E1).

«check my email, did inworld send me something?» — after a reset the archive held only the 30 newest unread
the connector had pulled, and the receipt was the 34th. The card's read answered from its summary: «nothing
from Inworld». Now:
  · a free-text read of the messaging card (`read_query`) ranks the archive by BM25 over EVERY word of the
    question — the rare word that names the sender outranks the filler, in any language;
  · words the archive has never seen are asked of the real mailbox (sender or subject), and what comes back is
    indexed, so the answer and the next question are local;
  · `search_archive` does the same when its own criteria find nothing.
"""
from __future__ import annotations

import time

import pytest

from connectors.messaging import archive
from widgets import store as wstore
from widgets.mensajeria import data

_RECEIPT = {"senderName": "Inworld AI", "chatId": "invoice+statements@inworld.ai", "messageId": "220440",
            "body": "[Asunto: Your receipt from Inworld AI #2281-4878]\nAmount paid $20.00",
            "subject": "Your receipt from Inworld AI #2281-4878", "timestamp": time.time() - 86400}


class _Mailbox:
    def __init__(self):
        self.asked: list = []


def _fake_search(mb, terms, limit=5, media_dir=None):
    mb.asked.append(list(terms))
    return [dict(_RECEIPT)] if any("inworld" in t for t in terms) else []


@pytest.fixture
def mailbox(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    from widgets.mensajeria import views
    views._MAILBOX_ASKED.clear()
    now = time.time()
    archive.record("email", "security@zapier.com", [
        {"messageId": "1", "from": "Zapier Security", "body": "Your password was reset. Any email to us…", "ts": now}],
        direction="in", chat_name="Zapier Security")
    mb = _Mailbox()
    monkeypatch.setattr("connectors.email.config.mailbox", lambda: mb)
    monkeypatch.setattr("connectors.email.search.search_text", _fake_search)
    yield mb
    archive.reset()


def test_a_read_about_an_unindexed_sender_finds_it_in_the_mailbox(mailbox):
    out = data.read_query("Has Inworld sent any email recently?")
    assert "Inworld AI" in out and "#2281-4878" in out, out
    assert any("inworld" in t for t in mailbox.asked[0]), "the unknown word is what goes to the mailbox"
    assert "email" not in mailbox.asked[0], "a word the archive already holds is not asked of the mailbox"


def test_what_the_mailbox_returned_is_indexed(mailbox):
    data.read_query("did inworld send me something?")
    assert archive.search("inworld"), "the mailbox's answer did not reach the archive"
    mailbox.asked.clear()
    data.read_query("did inworld send me something?")
    assert mailbox.asked == [], "an indexed sender, and words already asked, are answered locally"


def test_the_rare_word_outranks_the_filler(mailbox):
    data.read_query("inworld")                                  # index the receipt
    out = data.read_query("any email from inworld?")
    first = out.splitlines()[1]
    assert "Inworld AI" in first, out


def test_search_archive_asks_the_mailbox_when_nothing_is_indexed(mailbox):
    res = data.answer_action("search_archive", {"sender": "inworld"})["result"]
    assert res["count"] == 1 and res["matches"][0]["from"] == "Inworld AI"


def test_no_email_connector_means_no_mailbox_and_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    monkeypatch.setattr("connectors.email.config.mailbox", lambda: None)
    from widgets.mensajeria import views
    views._MAILBOX_ASKED.clear()
    assert data.read_query("did inworld write?") == ""
    archive.reset()


def test_what_the_mailbox_found_is_asked_into_the_card(mailbox, monkeypatch):
    """«open it» and «send the invoice» act on the CARD: the owner (its one writer) is asked to bring the mail in,
    through `search_archive` — the door that already queues the card's own load-previous order."""
    asked = []
    monkeypatch.setattr("widgets.supervisor.enqueue_from_thread", lambda wid, a, p: asked.append((wid, a, p)) or True)
    data.read_query("did inworld send me something?")
    assert ("mensajeria", "search_archive", {"q": "inworld", "platform": "email"}) in asked, asked


def test_query_is_read_as_q(mailbox):
    """Pass 31, E1: the model's first call was `search_archive {query: "Inworld"}` and was refused for lacking a
    criterion. `query` is what a search's text is called almost everywhere; it is read as `q`."""
    res = data.answer_action("search_archive", {"query": "inworld"})
    assert "result" in res and res["result"]["count"] == 1, res


def test_a_sender_the_archive_already_held_is_asked_into_the_card_too(tmp_path, monkeypatch):
    """Demo pass 38 (2026-09-29), E1→E3: «inworld» was already in the archive from an earlier session, so the
    mailbox was not searched — and the bring-back only ran after a mailbox search. The card never got the receipt:
    «open it» found no chat and the forward had no files. A sender the question names is brought back either way."""
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    from widgets.mensajeria import views
    views._MAILBOX_ASKED.clear()
    archive.record("email", "invoice+statements@inworld.ai", [dict(_RECEIPT, id="220440")], direction="in",
                   chat_name="Inworld AI")
    archive.record("email", "news@x.invalid", [{"id": "1", "body": "did you send the weekly news", "from": "News"}],
                   direction="in", chat_name="News")
    monkeypatch.setattr(views, "mailbox_fill", lambda terms: 0)          # the mailbox finds nothing new
    asked = []
    monkeypatch.setattr("widgets.supervisor.enqueue_from_thread", lambda wid, a, p: asked.append((wid, a, p)) or True)
    assert "Inworld" in data.read_query("did inworld send me something?")
    assert ("mensajeria", "search_archive", {"q": "inworld", "platform": "email"}) in asked, asked
    archive.reset()
