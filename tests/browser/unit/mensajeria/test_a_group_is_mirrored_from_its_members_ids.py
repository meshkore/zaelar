"""A contacts group is mirrored to WhatsApp from its members' ids, never their names read again (V2-854 F4).

Writer d's spec (`tests/memory/unit/contacts/test_a_group_end_to_end.py`, strict xfail «V2-854 gap»): a group made in
the contacts card names its people by id; `create_group` re-resolved each NAME through the send door, so a namesake
(«Raquel» with several Raquels) made the whole mirror refuse. Now an entry that is a contact's id is that row and goes
by its own channel (`directory.channel_for`), a contacts GROUP's id is its members, and a name is still a name.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def box(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    from widgets.contactos import data as cd
    from widgets.mensajeria import data as md
    ids = {}
    for key, name, handle in (("r1", "Raquel Soto", "+34600000101"), ("r2", "Raquel Jiménez", "+34600000102"),
                              ("j1", "Jordi Puig", "+34600000103"), ("l1", "Lucía Coll", "+34600000104"),
                              ("n1", "Nadia Ferrer", "")):
        cd.apply_action("add_contact", {"name": name})
        cid = next(c["id"] for c in cd.load_db()["contacts"] if c["name"] == name)
        if handle:
            cd.apply_action("set_channel", {"contactId": cid, "platform": "whatsapp", "handle": handle})
        ids[key] = cid
    return md, cd, ids


def test_members_named_by_id_are_mirrored_even_with_namesakes(box):
    md, _cd, ids = box
    r = md.apply_action("create_group", {"platform": "whatsapp", "name": "Padres del cole",
                                          "members": [ids["r1"], ids["j1"], ids["l1"]]})
    assert r["ok"] is True and r["result"]["members"] == ["Raquel Soto", "Jordi Puig", "Lucía Coll"], r
    order = md.load_db()["pending_group"][-1]
    assert [m["contactId"] for m in order["members"]] == [ids["r1"], ids["j1"], ids["l1"]]
    assert all(m["to"] or m["chatId"] for m in order["members"])


def test_a_contacts_group_id_is_its_members(box):
    md, cd, ids = box
    db = cd.load_db()
    db["contacts"].append({"id": "g-parents", "kind": "group", "name": "Padres", "members": [ids["r2"], ids["j1"]]})
    cd.store.save(cd.WIDGET_ID, db)
    r = md.apply_action("create_group", {"platform": "whatsapp", "name": "Padres", "members": ["g-parents"]})
    assert r["ok"] is True and r["result"]["members"] == ["Raquel Jiménez", "Jordi Puig"], r


def test_a_member_by_id_with_no_whatsapp_refuses_the_whole_group(box):
    md, _cd, ids = box
    r = md.apply_action("create_group", {"platform": "whatsapp", "name": "X", "members": [ids["j1"], ids["n1"]]})
    assert r["ok"] is False and "Nadia" in r["error"] and not md.load_db().get("pending_group")


def test_a_name_is_still_resolved_by_the_send_door(box):
    md, _cd, _ids = box
    assert md.apply_action("create_group", {"platform": "whatsapp", "name": "Y", "members": ["Jordi"]})["ok"]
    amb = md.apply_action("create_group", {"platform": "whatsapp", "name": "Z", "members": ["Raquel"]})
    assert amb["ok"] is False, "a namesake said by name is still a question"
