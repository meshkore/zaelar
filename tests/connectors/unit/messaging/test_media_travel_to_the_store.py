"""V2-543 — media stop dying at the store's field whitelist.

Measured before the fix: the WhatsApp bridge downloaded every image/video/audio/document and pushed the
absolute paths in `mediaUrls`; the strings mediaUrls/hasMedia/mediaType appeared in bridge.js and NOWHERE
in Python — the whitelist in `upsert_items` was the single line where they died, and the widget rendered
`[image received]` as plain text. These tests hold the whole media path: the fields travel, a file outside
the widget's data dir is COPIED in (the asset route serves ONLY that flat directory), and the disposal
queues (archive/trash) drain per platform.
"""
from __future__ import annotations

import os

import pytest


@pytest.fixture
def ms(tmp_path, monkeypatch):
    """ISOLATED widgets store — never the operator's real inbox or media."""
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    from connectors.messaging import store
    return store


def _msg(**over):
    base = {"messageId": "m1", "chatId": "c1", "senderId": "s1", "from": "Jose",
            "isGroup": False, "body": "hola", "urgencia": "media", "dirigido_a_mi": True}
    base.update(over)
    return base


def test_media_fields_travel_and_the_file_is_copied_into_the_servable_dir(ms, tmp_path):
    src = tmp_path / "outside" / "img_abc.jpg"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"\xff\xd8fake")
    ms.upsert_items("whatsapp", [_msg(body="[image received]", hasMedia=True, mediaType="image",
                                      mediaUrls=[str(src)], timestamp=1756742000)])
    it = ms.load()["items"][0]
    assert it["mediaType"] == "image"
    assert it["media"][0]["url"] == "/widgets/mensajeria/asset/img_abc.jpg"
    assert abs(it["ts"] - 1756742000) < 1
    from widgets import store as wstore
    assert os.path.isfile(os.path.join(wstore.data_dir("mensajeria"), "img_abc.jpg")), \
        "a file outside the flat data dir is unreachable by the asset route — it must be copied in"


def test_a_missing_media_file_never_blocks_the_message(ms):
    ms.upsert_items("whatsapp", [_msg(hasMedia=True, mediaType="image", mediaUrls=["/no/such/file.jpg"])])
    it = ms.load()["items"][0]
    assert it["body"] == "hola" and "media" not in it, "the message lands with or without its picture"
    assert it["mediaType"] == "image", "the TYPE still travels so the widget can say what it was"


def test_without_media_the_entry_shape_is_unchanged(ms):
    ms.upsert_items("telegram", [_msg()])
    it = ms.load()["items"][0]
    assert "media" not in it and "mediaType" not in it
    assert it["ts"] > 0, "a message with no connector timestamp still gets arrival time"


def test_newest_first_within_the_same_urgency(ms):
    ms.upsert_items("whatsapp", [
        _msg(messageId="old", timestamp=100),
        _msg(messageId="new", timestamp=200),
        _msg(messageId="urgent", timestamp=50, urgencia="alta"),
    ])
    order = [i["messageId"] for i in ms.load()["items"]]
    assert order == ["urgent", "new", "old"], order


def test_disposal_queues_drain_per_platform_and_consume(ms):
    db = ms.load()
    db["pending_archive"] = [{"platform": "email", "messageId": "1"},
                             {"platform": "whatsapp", "messageId": "2"}]
    ms.save(db)
    mine = ms.take_pending_disposal("archive", "email")
    assert [k["messageId"] for k in mine] == ["1"]
    assert [k["messageId"] for k in ms.load()["pending_archive"]] == ["2"], "other platforms stay queued"
    assert ms.take_pending_disposal("trash", "email") == []


def test_the_bus_topics_for_disposal_exist_and_never_raise(ms):
    from connectors.messaging import ingest
    assert ingest.TOPIC_ARCHIVE == "msg.archive" and ingest.TOPIC_TRASH == "msg.trash"
    ingest.publish_archive({"platform": "email", "messageId": "1"})   # loop-agnostic, never raises
    ingest.publish_trash(None)


def test_telegram_composite_message_id_parses_for_watermark_and_threading():
    """int('<chat>:<id>') always raised, so replies silently lost `reply_to` and mark-read ignored the
    message id — the composite is OURS (service._normalize), the parser must know its own wire format."""
    from connectors.telegram.service import _tg_msg_id
    assert _tg_msg_id("-100123:456") == 456
    assert _tg_msg_id("789") == 789
    assert _tg_msg_id("x") is None and _tg_msg_id(None) is None
