"""V2-616 — a thread remembers whether it is a GROUP, at the THREAD level, forever.

The operator's report: in a 1:1 WhatsApp chat, every single message repeated the contact's name — the header
above the thread already names who this is, so the repetition was pure noise. The fix (widget.js) is to only
print a sender name on a bubble when the thread is a GROUP, where there is no single "who this is" for the
header to say once.

The naive read is "check `isGroup` on the message" — but `thread.py::_norm` never kept that field on a stored
entry (only `id/dir/who/body/read/ts/mediaType/media` survive), and `data.py::_thread_view` only re-attaches it
from a message that is STILL PENDING (unread). So a mostly-read group thread would silently look like a 1:1
by the time the widget asks — the group flag has to live on the THREAD, set once and never cleared.
"""
from __future__ import annotations

import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]
GROUP_CHAT = "34654243954-1473186357@g.us"
DM_CHAT = "34600@s.whatsapp.net"


@pytest.fixture
def store(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real inbox (same pattern as test_the_widget_follows_the_real_app.py)."""
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    from connectors.messaging import store as ms
    from widgets.mensajeria import thread
    return ms, thread


def test_a_group_message_marks_its_thread_as_a_group(store):
    ms, thread = store
    ms.upsert_items("whatsapp", [{
        "messageId": "g1", "chatId": GROUP_CHAT, "senderId": "34600", "from": "Elena",
        "isGroup": True, "group": "Ex alumnos", "body": "Hola a todos", "urgencia": "media",
        "timestamp": 1000.0}])
    meta = thread.meta(ms.load(), "whatsapp", GROUP_CHAT)
    assert meta["isGroup"] is True, meta


def test_a_direct_message_never_marks_its_thread_as_a_group(store):
    ms, thread = store
    ms.upsert_items("whatsapp", [{
        "messageId": "d1", "chatId": DM_CHAT, "senderId": "34600", "from": "Jose Vicente",
        "isGroup": False, "body": "Estoy aquí", "urgencia": "media", "timestamp": 1000.0}])
    meta = thread.meta(ms.load(), "whatsapp", DM_CHAT)
    assert meta["isGroup"] is False, meta


def test_the_flag_survives_once_the_group_message_is_read(store):
    """The exact gap a per-MESSAGE flag would have: reading a message drops its live `isGroup` copy
    (data.py's `_thread_view` only re-attaches it from a still-PENDING item) — the thread-level flag must not
    depend on any message still being unread."""
    ms, thread = store
    ms.upsert_items("whatsapp", [{
        "messageId": "g2", "chatId": GROUP_CHAT, "senderId": "34600", "from": "Elena",
        "isGroup": True, "group": "Ex alumnos", "body": "Hola a todos", "urgencia": "media",
        "timestamp": 1000.0}])
    from widgets.mensajeria import data as d
    d.apply_action("clear")  # marks every pending item read, the widget's own "Limpiar"
    meta = thread.meta(ms.load(), "whatsapp", GROUP_CHAT)
    assert meta["isGroup"] is True, "a read group thread must still say it is a group"


def test_a_thread_that_never_learns_isgroup_defaults_to_false(store):
    """No message ever arrived with `isGroup`, or the thread does not exist yet — never crash, never claim a
    group that was never seen."""
    ms, thread = store
    assert thread.meta(ms.load(), "whatsapp", "nonexistent@lid")["isGroup"] is False
