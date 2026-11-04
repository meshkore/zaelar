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


def test_a_chat_is_linked_by_its_phone_and_found_by_either_name(ct):
    """His rule (2026-11-04): contacts are linked by phone or email. The chat «Pablo Sabin» (a @lid whose session
    mapping knows the phone) is the «Pablo FF» of his address book — one person, found by both names; the import
    never renames the row he has."""
    d, directory = ct
    from widgets.contactos import imports
    db = d.load_db()
    db["contacts"].append({"id": "g9", "kind": "person", "name": "Pablo FF", "phone": "678 51 43 78", "channels": []})
    rows = [wa.person_of_chat({**_chat("105475857223747@lid", "Pablo Sabin"), "phoneNumber": "34678514378"})]
    got = imports.merge_contacts(db, rows, source="whatsapp")
    assert got["added"] == 0 and got["filled"] == 1, "matched by the phone, not added beside him"
    d.store.save(d.WIDGET_ID, db)
    pablo = next(c for c in d.load_db()["contacts"] if c["id"] == "g9")
    assert pablo["name"] == "Pablo FF" and pablo["channels"][0]["chatId"] == "105475857223747@lid"
    assert [c["id"] for c in directory.resolve("Pablo Sabin")] == ["g9"]
    assert directory.resolve("Pablo")[0]["id"] == "g9", "the Pablo he talks to comes first"
    assert [r["name"] for r in d.people_named("pregunta a pablo sabin si ha probado zaelar")] == ["Pablo FF"]


def test_the_bridge_hands_the_phone_of_a_linked_identity():
    import pathlib
    src = (pathlib.Path(wa.__file__).parents[1] / "bridge" / "bridge.js").read_text(encoding="utf-8")
    assert "lidToPhone[lid]" in src and "phoneNumber" in src.split("app.get('/chats'")[1].split("app.post(")[0]


def test_asked_about_the_chat_name_the_record_says_it_is_the_same_person(ct):
    d, _directory = ct
    from widgets.contactos import imports, lookup
    db = d.load_db()
    db["contacts"].append({"id": "g9", "kind": "person", "name": "Pablo FF", "phone": "678 51 43 78", "channels": []})
    imports.merge_contacts(db, [wa.person_of_chat({**_chat("105475857223747@lid", "Pablo Sabin"),
                                                    "phoneNumber": "34678514378"})], source="whatsapp")
    d.store.save(d.WIDGET_ID, db)
    ans = lookup.read_query("Is there a contact named Pablo Sabin?")
    assert "«Pablo FF»" in ans and "también se llama «Pablo Sabin»" in ans


def test_his_word_for_the_chat_names_the_contact_it_is_linked_to(ct):
    """«pregunta a Pablo Sabin…» then «sí, es él» → `send_to {contact: "Pablo FF"}`: the person he named, by the
    name his chat shows — no «are you sure?» over a recipient he did name."""
    d, _directory = ct
    from widgets.contactos import imports
    from nucleo.acts import message as gate
    db = d.load_db()
    db["contacts"].append({"id": "g9", "kind": "person", "name": "Pablo FF", "phone": "678 51 43 78", "channels": []})
    imports.merge_contacts(db, [wa.person_of_chat({**_chat("105475857223747@lid", "Pablo Sabin"),
                                                    "phoneNumber": "34678514378"})], source="whatsapp")
    d.store.save(d.WIDGET_ID, db)
    assert gate.is_his("Pablo FF", ["Pablo Sabin"]) is True
    assert gate.is_his("Pablo FF", ["ask Pablo Hernandez"]) is False


def test_the_people_block_says_the_chat_name_is_the_same_person(ct):
    d, _directory = ct
    from widgets.contactos import imports
    db = d.load_db()
    db["contacts"].append({"id": "g9", "kind": "person", "name": "Pablo FF", "phone": "678 51 43 78", "channels": []})
    imports.merge_contacts(db, [wa.person_of_chat({**_chat("105475857223747@lid", "Pablo Sabin"),
                                                    "phoneNumber": "34678514378"})], source="whatsapp")
    d.store.save(d.WIDGET_ID, db)
    from nucleo.turn.prompt import builder
    block = builder._people_block("Pablo Sabin, el de WhatsApp")
    assert "· Pablo FF (también «Pablo Sabin»)" in block
