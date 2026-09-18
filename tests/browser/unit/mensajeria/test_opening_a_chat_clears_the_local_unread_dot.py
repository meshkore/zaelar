"""Opening a chat IS reading it (locally): the unread dot must clear.

Reported live (session 6d19df41): the operator opened Raquel's chat, read the
conversation, went back — and the unread dot was still there, «totally wrong».

Root cause: `apply_action("open")` only set `active_chat` (pure navigation) and
never flipped the thread-store `read` flags. The activity lens dot
(`activityList` in widget.js, `tcount`) reads exactly those flags via
`views._activity_chats`, and nothing on the open path ever cleared them.

Scope, deliberately narrow: only the LOCAL flags flip. Nothing is enqueued to
`pending_read`, so the real app is untouched — marking read over there stays an
explicit `read`, never a side effect of navigating. The pending inbox items
stay too: attention-pending is a separate state from having-looked.
"""
from __future__ import annotations

import time

from widgets import store as wstore
from widgets.mensajeria import data, views


def _seed(now=None):
    now = now or time.time()
    db = data.load_db()
    db["threads"] = {"whatsapp|raquel": {
        "name": "Raquel", "isGroup": False, "complete": True, "touched": now,
        "msgs": [
            {"id": "m1", "dir": "in", "who": "Raquel", "body": "hola", "ts": now - 300,
             "read": False},
            {"id": "m2", "dir": "in", "who": "Raquel", "body": "sigues ahi?", "ts": now - 200,
             "read": False},
        ]}}
    db["items"] = [{"messageId": "m2", "chatId": "raquel", "platform": "whatsapp",
                    "from": "Raquel", "group": "Raquel", "body": "sigues ahi?",
                    "ts": now - 200, "urgencia": "media"}]
    db["pending_read"] = []
    db["active_chat"] = None
    wstore.save("mensajeria", db)
    return db


def _unread_dot(db):
    rows = views._activity_chats(db, "whatsapp", 72.0)
    assert len(rows) == 1
    return rows[0]["unread"]


def test_open_by_identity_clears_the_local_unread_dot(tmp_path, monkeypatch):
    """THE case: click on the activity row opens by identity and the dot clears."""
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    _seed()
    data.apply_action("open", {"platform": "whatsapp", "chatId": "raquel"})
    db = data.load_db()
    assert db["active_chat"] == {"platform": "whatsapp", "chatId": "raquel"}
    assert _unread_dot(db) == 0, "the activity lens dot reads the thread flags"
    assert db["pending_read"] == [], "no outward write: the real app is untouched"
    assert len(db["items"]) == 1, "pending-attention state is separate from having looked"


def test_open_by_number_clears_the_local_unread_dot(tmp_path, monkeypatch):
    """Same through the chat-list numbering ([[msg.open:N]] by voice)."""
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    _seed()
    data.apply_action("open", {"n": 1})
    db = data.load_db()
    assert db["active_chat"] == {"platform": "whatsapp", "chatId": "raquel"}
    assert _unread_dot(db) == 0
    assert db["pending_read"] == [], "no outward write: the real app is untouched"
