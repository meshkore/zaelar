#
# test_a_search_that_names_a_sender_starts_with_its_mail.py — demo pass 37 (2026-09-29), E1-E3.
#
# «check my email, did inworld send me something?» → `search_archive {"query": "inworld"}`. Newest first, the top
# rows were our own forwards of the receipt to Andrew from earlier runs; «open it» then opened our mail to Andrew
# and the forward went out with the wrong message. The receipt FROM Inworld was in the archive, below them. A
# query that names a sender starts with that sender's own messages.
#
import pytest

from connectors.messaging import archive
from widgets import store as wstore
from widgets.mensajeria import views


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    archive.reset()
    archive.record("email", "invoice@inworld.ai", [{"id": "orig", "ts": 1000, "from": "Inworld AI",
                   "body": "[Asunto: Your receipt from Inworld AI #2281-4878] $25.00"}], direction="in",
                   chat_name="Inworld AI")
    for i in range(10):
        archive.record("email", "ago@x.invalid", [{"id": f"fw{i}", "ts": 2000 + i,
                       "body": "Hi Andrew, forwarding the Inworld receipt — please book it."}], direction="out")
    archive.record("email", "news@x.invalid", [{"id": "n1", "ts": 1500, "from": "Newsletter",
                   "body": "Weekly digest"}], direction="in")
    yield
    archive.reset()


def test_the_named_senders_mail_comes_first():
    rows = views.archive_rows({"query": "inworld"})
    assert rows[0]["msg_id"] == "orig", [(r["direction"], r["body"][:30]) for r in rows[:3]]
    assert any(r["msg_id"].startswith("fw") for r in rows), "the other matches are still there, after it"


def test_a_query_that_names_nobody_keeps_newest_first():
    rows = views.archive_rows({"query": "receipt"})
    assert rows[0]["ts"] >= rows[-1]["ts"]


def test_an_explicit_sender_is_left_alone():
    rows = views.archive_rows({"query": "book", "sender": "Newsletter"})
    assert rows == []
