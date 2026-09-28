"""The card's digest says what it just SENT (demo pass 2026-09-28, full18 C5b).

The Telegram to Ethan went out; the next turn said «let me just send that to Ethan first» — nothing the model reads
said it had been sent, because the digest is the inbox and the inbox is what came IN."""
import time

import pytest


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data
    return data


def test_a_message_sent_minutes_ago_is_in_the_digest(md):
    from widgets.mensajeria import inbox_read
    db = md.load_db()
    db["threads"] = {"telegram|555": {"name": "Ethan", "msgs": [
        {"id": "1", "dir": "out", "who": "Tú", "body": "Moved to 4:15, see you then", "ts": time.time() - 120}]}}
    md.store.save(md.WIDGET_ID, db)
    d = inbox_read.prompt_digest()
    assert "ENVIADO por telegram a Ethan" in d and "Moved to 4:15" in d, d


def test_an_old_send_and_what_came_in_are_not_reported_as_sent(md):
    from widgets.mensajeria import inbox_read
    db = md.load_db()
    db["threads"] = {"telegram|555": {"name": "Ethan", "msgs": [
        {"id": "1", "dir": "out", "body": "last week", "ts": time.time() - 7 * 86400},
        {"id": "2", "dir": "in", "body": "hi there", "ts": time.time() - 60}]}}
    md.store.save(md.WIDGET_ID, db)
    assert "ENVIADO" not in inbox_read.prompt_digest()


def test_a_send_still_leaving_says_do_not_send_it_again(md):
    from widgets.mensajeria import inbox_read
    db = md.load_db()
    db["pending_send"] = [{"platform": "telegram", "name": "Ethan", "text": "Moved to 4:15", "not_before": time.time() + 5}]
    md.store.save(md.WIDGET_ID, db)
    d = inbox_read.prompt_digest()
    assert "SALIENDO" in d and "no lo envíes otra vez" in d
