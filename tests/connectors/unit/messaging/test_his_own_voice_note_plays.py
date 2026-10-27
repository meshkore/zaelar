"""His OWN voice notes play in the conversation, like the ones he receives (V2-819).

The operator, in a WhatsApp chat: the voice notes he receives show a player, the ones he sent show only «audio».
The bridge downloads a voice note he sends from his phone exactly as one he receives and hands over the same
`mediaUrls`; only the INBOUND door (`upsert_items`) turned those paths into `media` entries the card can play —
the outbound door (`record_outbound`) stored them raw. Now both go through `store.with_media`, and a re-delivery
of the same message without media (the card's own echo of a send) never strips the player off it.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ms(tmp_path, monkeypatch):
    """ISOLATED widgets store — never the operator's real inbox or media."""
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    from connectors.messaging import store
    return store


def _thread_msgs(ms, chat):
    return ms.load()["threads"][f"whatsapp|{chat}"]["msgs"]


def test_a_voice_note_he_sent_from_his_phone_reaches_the_thread_playable(ms, tmp_path):
    src = tmp_path / "bridge-cache" / "aud_9f8e7d.ogg"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"OggS-fake")
    chat = "34600000001@s.whatsapp.net"
    ms.record_outbound("whatsapp", chat, {"messageId": "OUT1", "chatId": chat, "body": "[ptt received]",
                                          "hasMedia": True, "mediaType": "ptt", "mediaUrls": [str(src)],
                                          "direction": "out", "timestamp": 1761550000})
    m = _thread_msgs(ms, chat)[-1]
    assert m["dir"] == "out" and m["mediaType"] == "ptt"
    assert m["media"][0]["url"] == "/widgets/mensajeria/asset/aud_9f8e7d.ogg", m


def test_a_redelivery_without_media_keeps_the_player():
    """The conversation's own rule, on the row itself: a second delivery of one message fills in, never empties."""
    from widgets.mensajeria import thread
    db = {}
    media = [{"url": "/widgets/mensajeria/asset/aud_1.ogg", "type": "ptt", "name": "aud_1.ogg"}]
    thread.append(db, "whatsapp", "c1", {"messageId": "OUT2", "body": "", "mediaType": "ptt", "media": media}, "out")
    thread.append(db, "whatsapp", "c1", {"messageId": "OUT2", "body": ""}, "out")
    m = db["threads"]["whatsapp|c1"]["msgs"][-1]
    assert m.get("media") == media and m["mediaType"] == "ptt", "the echo filled in nothing and emptied nothing"


def test_both_doors_are_one_function(ms, tmp_path):
    """The inbound door still does exactly what it did — through the same function the outbound one uses."""
    src = tmp_path / "img_a.jpg"
    src.write_bytes(b"\xff\xd8")
    raw = {"messageId": "IN1", "chatId": "c2", "body": "[image received]", "hasMedia": True,
           "mediaType": "image", "mediaUrls": [str(src)]}
    assert ms.with_media(raw)["media"][0]["url"].endswith("/img_a.jpg")
    ms.upsert_items("whatsapp", [{**raw, "from": "Ana", "urgencia": "media"}])
    assert ms.load()["items"][0]["media"][0]["url"].endswith("/img_a.jpg")
