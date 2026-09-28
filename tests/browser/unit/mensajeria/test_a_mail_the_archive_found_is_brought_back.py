"""A mail the archive finds but the card no longer holds is asked back from the mailbox (demo pass 2026-09-28,
full28 E1→E3: the card holds the 30 most recent unread; with newer mail since, the Inworld receipt had fallen out —
«open it» found no chat and «send the invoice to andrew» had nothing to forward, while the archive had it all along)."""
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data, views
    rows = [{"platform": "email", "direction": "in", "chat_id": "invoice@inworld.ai", "msg_id": "220440",
             "sender": "Inworld AI", "ts": 1.0, "body": "receipt"},
            {"platform": "email", "direction": "out", "chat_id": "andrew@example.com", "msg_id": "", "ts": 2.0}]
    monkeypatch.setattr(views, "archive_rows", lambda payload: rows)
    return data


def test_the_found_mail_is_asked_back_just_below_its_uid(md):
    md.apply_action("search_archive", {"q": "inworld"})
    orders = md.load_db()["pending_history"]
    assert orders == [{"platform": "email", "chatId": "invoice@inworld.ai", "beforeTs": 0, "beforeId": "220441",
                       "limit": 1}], orders


def test_a_mail_the_card_already_holds_is_not_asked_again(md):
    db = md.load_db()
    db["threads"] = {"email|invoice@inworld.ai": {"name": "Inworld AI", "msgs": []}}
    md.store.save(md.WIDGET_ID, db)
    md.apply_action("search_archive", {"q": "inworld"})
    assert md.load_db().get("pending_history") == []


def test_a_mail_brought_back_carries_its_files():
    src = (ENGINE / "connectors/email/service.py").read_text("utf-8")
    i = src.index("async def _drain_history")
    assert '"media": store._media_entries(m)' in src[i:i + 2500]
