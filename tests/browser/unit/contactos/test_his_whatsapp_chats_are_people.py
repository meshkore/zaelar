"""V2-850 · the people he talks to on WhatsApp are in his directory: the import reads the CHAT book, not only the
address book.

Measured on his own engine (2026-11-04): the bridge's address book held 4 contacts — a linked device is told almost
nothing of the phone's contacts — while its chat book named 200+ conversations. «Pablo Sabin» and «Rakel Karó»
existed only there, so «pregunta a Pablo si ha probado Zaelar» could never reach the Pablo he writes to: fourteen
«Pablo» rows from an old Google import came back instead, none of them reachable on WhatsApp.

  · a named one-to-one chat is a person: name, the chat to reach them, and when they last talked (so the directory
    reads them as ACTIVE, closest first);
  · a group, a feed, or a chat named only by its number is not;
  · the import is the contacts card's own merge, so a chat already folded in is matched, never duplicated.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from connectors.whatsapp.service import directory as wa


def _chat(jid, name, ts=None, group=False):
    return {"id": jid, "name": name, "isGroup": group, "ts": ts if ts is not None else time.time() - 86400}


def test_a_named_chat_is_a_person_and_the_rest_are_not():
    p = wa.person_of_chat(_chat("105475857223747@lid", "Pablo Sabin"))
    assert p["name"] == "Pablo Sabin" and p["phone"] == "", "a @lid is not a phone number"
    ch = p["channels"][0]
    assert ch["chatId"] == "105475857223747@lid" and ch["source"] == "chat" and ch["last_seen"] > 0
    assert wa.person_of_chat(_chat("34600000001@s.whatsapp.net", "Rowan Lee"))["phone"] == "+34600000001"
    assert wa.person_of_chat(_chat("120363000@g.us", "Familia", group=True)) is None
    assert wa.person_of_chat(_chat("status@broadcast", "Status")) is None
    assert wa.person_of_chat(_chat("126018786480272@lid", "126018786480272")) is None, "a number is not a name"


def test_the_chat_book_is_read_page_by_page(monkeypatch):
    pages = [{"chats": [_chat("1@lid", "Rakel Karó", 300), _chat("2@g.us", "Grupo", 290, group=True)],
              "complete": False},
             {"chats": [_chat("3@lid", "Pablo Sabin", 200)], "complete": True}]
    asked = []

    async def get_chats(before=None, limit=20):
        asked.append(before)
        return pages[len(asked) - 1]
    monkeypatch.setattr(wa.client, "get_chats", get_chats)
    people = asyncio.run(wa.chat_people(set()))
    assert [p["name"] for p in people] == ["Rakel Karó", "Pablo Sabin"] and asked == [None, 290.0]
    asked.clear()
    assert asyncio.run(wa.chat_people({"1@lid", "3@lid"})) == [], "the address book already gave them"


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    directory._WINDOW.clear()
    from widgets.contactos import data as d
    db = d.load_db()
    for i, n in enumerate(["Psm Pablo Buso", "Pablo Elastic", "Pablo Hernandez"]):
        db["contacts"].append({"id": f"g{i}", "kind": "person", "name": n, "channels": []})
    d.store.save(d.WIDGET_ID, db)
    yield d, directory
    directory._WINDOW.clear()


def test_imported_he_is_the_pablo_he_talks_to(ct):
    d, directory = ct
    from widgets.contactos import imports
    db = d.load_db()
    rows = [wa.person_of_chat(_chat("105475857223747@lid", "Pablo Sabin"))]
    assert imports.merge_contacts(db, rows, source="whatsapp")["added"] == 1
    assert imports.merge_contacts(db, rows, source="whatsapp")["added"] == 0, "the same chat is matched, not doubled"
    d.store.save(d.WIDGET_ID, db)
    hits = directory.resolve("Pablo")
    assert hits[0]["name"] == "Pablo Sabin" and directory.level(hits[0]) == directory.ACTIVE
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": "Pablo Sabin", "text": "¿has probado Zaelar?"})
    assert t["ok"] is True and t["platform"] == "whatsapp" and t["chatId"] == "105475857223747@lid"


def test_the_import_the_card_asks_for_carries_the_chats(monkeypatch):
    """The wiring: «sync WhatsApp» on the contacts card is `_drain_contacts`, and it must hand over the chats too."""
    class _Inbox:
        def drain(self):
            return [{"platform": "whatsapp"}]

    async def get_contacts():
        return {"contacts": [{"id": "34600000001@s.whatsapp.net", "name": "Rowan Lee"}], "groups": [], "partial": True}

    async def get_chats(before=None, limit=20):
        return {"chats": [_chat("105475857223747@lid", "Pablo Sabin"), _chat("34600000001@s.whatsapp.net", "Rowan")],
                "complete": True}
    sent = []
    monkeypatch.setattr(wa._svc, "_contacts_inbox", _Inbox())
    monkeypatch.setattr(wa.client, "get_contacts", get_contacts)
    monkeypatch.setattr(wa.client, "get_chats", get_chats)
    monkeypatch.setattr(wa.ingest, "publish_contacts", lambda p, people, groups, **k: sent.append(people))
    asyncio.run(wa._drain_contacts())
    assert [p["name"] for p in sent[0]] == ["Rowan Lee", "Pablo Sabin"], "his saved name wins; the chat adds Pablo"
