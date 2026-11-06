"""WhatsApp and Telegram send files the way their apps do, and create groups (the connector half).

WhatsApp: each file through the bridge's /send-media, the text as the first file's caption — except a voice
note, which carries none, so the text then goes on its own. Telegram: several photos/videos as ONE album with the
text as caption, a voice note as a voice note. Both re-check that every file is inside the messaging widget's data
dir before it leaves, and both hand a new group back as a chat-list row.
"""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest



@pytest.fixture
def files(tmp_path, monkeypatch):
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    folder = wstore.data_dir("mensajeria")

    def make(name):
        p = os.path.join(folder, name)
        open(p, "wb").write(b"x")
        return os.path.realpath(p)
    outside = tmp_path / "elsewhere.jpg"
    outside.write_bytes(b"x")
    return SimpleNamespace(make=make, outside=str(outside))


class _Inbox:
    def __init__(self, orders):
        self._o = orders

    def drain(self):
        out, self._o = self._o, []
        return out


def test_whatsapp_sends_files_with_the_caption_where_the_app_puts_it(files, monkeypatch):
    from connectors.whatsapp import client, service
    calls = []

    async def send_media(chat, path, caption=""):
        calls.append(("media", os.path.basename(path), caption))
        return {"messageId": "M"}

    async def send_message(chat, text, reply_to=None):
        calls.append(("text", text))
        return {"messageId": "T"}
    monkeypatch.setattr(client, "send_media", send_media)
    monkeypatch.setattr(client, "send_message", send_message)
    photo, doc = files.make("up_a_foto.jpg"), files.make("up_b_factura.pdf")
    asyncio.run(service._send("1@s.whatsapp.net", "mira", [photo, doc, files.outside]))
    assert calls == [("media", "up_a_foto.jpg", "mira"), ("media", "up_b_factura.pdf", "")], \
        "the text is the first file's caption; a file outside the widget dir never leaves"
    calls.clear()
    asyncio.run(service._send("1@s.whatsapp.net", "escúchalo", [files.make("up_c_nota.ogg")]))
    assert calls == [("media", "up_c_nota.ogg", ""), ("text", "escúchalo")], "a voice note carries no caption"


def test_telegram_sends_an_album_and_a_voice_note_as_its_app_does(files, monkeypatch):
    from connectors.telegram import service
    calls = []

    class _C:
        async def send_file(self, peer, f, **kw):
            calls.append(("file", [os.path.basename(x) for x in (f if isinstance(f, list) else [f])],
                          kw.get("caption"), kw.get("voice_note", False)))
            return [SimpleNamespace(id=1)] if isinstance(f, list) else SimpleNamespace(id=2)

        async def send_message(self, peer, text, **kw):
            calls.append(("text", text))
            return SimpleNamespace(id=3)
    monkeypatch.setattr(service, "_client", _C())
    a, b, v = files.make("up_a_1.jpg"), files.make("up_b_2.mp4"), files.make("up_c_3.ogg")
    asyncio.run(service._send(42, "las fotos", [a, b, v]))
    assert calls == [("file", ["up_a_1.jpg", "up_b_2.mp4"], "las fotos", False),
                     ("file", ["up_c_3.ogg"], None, True)]


def test_mark_as_unread_reaches_whatsapp_and_telegram(monkeypatch):
    """«Déjalo como no leído» was email-only, so on WhatsApp the model reached for `dismiss` — the opposite.
    Both apps mark a CHAT unread; each connector now does it."""
    from connectors.telegram import service as tg
    from connectors.whatsapp import client, service as wa
    got = []

    async def mark_unread(key):
        got.append(("wa", key["chatId"], key["messageId"]))
        return {"success": True}
    monkeypatch.setattr(client, "mark_unread", mark_unread)
    monkeypatch.setattr(wa, "_unread_inbox", _Inbox([{"platform": "whatsapp", "chatId": "1@s.whatsapp.net",
                                                      "messageId": "M1", "ts": 1}]))
    asyncio.run(wa._drain_unread())

    class _C:
        async def get_input_entity(self, ref):
            return SimpleNamespace(ref=ref)

        async def __call__(self, req):
            got.append(("tg", type(req).__name__, req.unread, req.peer.peer.ref))
    monkeypatch.setattr(tg, "_client", _C())
    monkeypatch.setattr(tg, "_unread_inbox", _Inbox([{"platform": "telegram", "chatId": "-1001", "messageId": "-1001:7"}]))
    asyncio.run(tg._drain_unread())
    assert got == [("wa", "1@s.whatsapp.net", "M1"), ("tg", "MarkDialogUnreadRequest", True, -1001)]
