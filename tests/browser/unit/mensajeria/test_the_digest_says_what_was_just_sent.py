"""The card's digest says what it just SENT (demo pass 2026-09-28, full18 C5b).

The Telegram to Rowan went out; the next turn said «let me just send that to Rowan first» — nothing the model reads
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
    db["threads"] = {"telegram|555": {"name": "Rowan", "msgs": [
        {"id": "1", "dir": "out", "who": "Tú", "body": "Moved to 4:15, see you then", "ts": time.time() - 120}]}}
    md.store.save(md.WIDGET_ID, db)
    d = inbox_read.prompt_digest()
    assert "ENVIADO por telegram a Rowan" in d and "Moved to 4:15" in d, d


def test_an_old_send_and_what_came_in_are_not_reported_as_sent(md):
    from widgets.mensajeria import inbox_read
    db = md.load_db()
    db["threads"] = {"telegram|555": {"name": "Rowan", "msgs": [
        {"id": "1", "dir": "out", "body": "last week", "ts": time.time() - 7 * 86400},
        {"id": "2", "dir": "in", "body": "hi there", "ts": time.time() - 60}]}}
    md.store.save(md.WIDGET_ID, db)
    assert "ENVIADO" not in inbox_read.prompt_digest()


def test_a_send_still_leaving_says_do_not_send_it_again(md):
    from widgets.mensajeria import inbox_read
    db = md.load_db()
    db["pending_send"] = [{"platform": "telegram", "name": "Rowan", "text": "Moved to 4:15", "not_before": time.time() + 5}]
    md.store.save(md.WIDGET_ID, db)
    d = inbox_read.prompt_digest()
    assert "SALIENDO" in d and "no lo envíes otra vez" in d


def test_searching_the_archive_is_a_read_that_answers_and_brings_the_card():
    """full21 E1→E2: «did inworld send me something?» was answered by `search_archive` with the card closed — the
    action counted as a WRITE (it was not declared a view), so no card came; «open it» then had nothing on screen
    to point at and opened the inbox."""
    from widgets import effects as fx
    assert fx.carries("mensajeria", "search_archive", fx.DATA_READ)
    assert not fx.carries("mensajeria", "search_archive", fx.DATA_WRITE)
    assert fx.carries("mensajeria", "search_archive", fx.OUTPUT_ANSWER)


def test_a_forward_without_its_note_is_refused_in_its_own_name():
    """full21 E3: `forward {contact: Quinn}` was refused in words that named `send_to`, and the same-turn correction
    retried the wrong action. The refusal names forward and asks for the note."""
    from widgets.mensajeria import data
    got = data.answer_action("forward", {"contact": "Quinn"})
    assert got["ok"] is False and "forward" in got["error"] and "send_to" not in got["error"]
