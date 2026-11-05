"""V2-854 F0 · a group, end to end: made by name, members added and removed, mirrored to WhatsApp, written to.

The conversation it serves: «créame un grupo con los padres del colegio» → «¿quiénes?» → three people → the group
exists with them; «haz el grupo también en WhatsApp» → a WhatsApp group with the same people; «mándale un mensaje a
este grupo» → the group is ONE recipient. Today a contacts group is a LABEL on each member (`groups`), and a WhatsApp
group is a directory row of `kind: group`; F1 makes the contacts group a collection with ids (an empty group can
exist, a rename keeps its members). Everything runs on the synthetic directory, through the cards' own actions; the
WhatsApp side stops at the order the connector drains (`pending_group`) — nothing is sent anywhere.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

F1 = pytest.mark.xfail(strict=True, reason="V2-854 F1: groups are a collection with ids, not only a label on members")

PARENTS = ("lucia-active", "active-jordy", "fav-rakel")       # three people, each with a WhatsApp chat
GROUP_ES, GROUP_EN = "Padres del colegio", "School parents"


def _rail(cd) -> dict:
    return {g["id"]: g["count"] for g in cd.view_data()["groups"]}


def _row(cd, cid: str) -> dict:
    return next(c for c in cd.load_db()["contacts"] if c["id"] == cid)


def _label(cd, cid: str, group: str):
    return cd.apply_action("update_contact", {"contactId": cid, "group": group})


@pytest.mark.parametrize("group", [GROUP_ES, GROUP_EN], ids=["es", "en"])
def test_a_group_is_made_with_the_people_he_names(directory_world, group):
    cd, _d, _rows = directory_world
    for cid in PARENTS:
        assert _label(cd, cid, group)["ok"] is True
    assert _rail(cd).get(group) == 3
    shown = cd.apply_action("show_view", {"group": group.lower()})
    assert {c["id"] for c in cd.model.matches(cd.visible(cd.load_db()), group=group)} == set(PARENTS), shown


def test_a_member_is_removed_and_the_others_stay(directory_world):
    cd, _d, _rows = directory_world
    for cid in PARENTS:
        _label(cd, cid, GROUP_ES)
    gone = PARENTS[1]
    keep = [g for g in _row(cd, gone)["groups"] if g != GROUP_ES]
    assert cd.apply_action("update_contact", {"contactId": gone, "groups": keep})["ok"] is True
    assert _rail(cd).get(GROUP_ES) == 2 and GROUP_ES not in _row(cd, gone)["groups"]
    assert all(GROUP_ES in _row(cd, cid)["groups"] for cid in PARENTS if cid != gone)


def test_a_contact_in_two_groups_counts_in_both(directory_world):
    cd, _d, _rows = directory_world
    for cid in PARENTS:
        _label(cd, cid, GROUP_ES)
    _label(cd, PARENTS[0], "Pádel")
    rail = _rail(cd)
    assert rail.get(GROUP_ES) == 3 and rail.get("Pádel") == 1
    assert _row(cd, PARENTS[0])["groups"] == [GROUP_ES, "Pádel"]


def _groups_collection() -> dict:
    manifest = json.loads((Path(__file__).resolve().parents[4] / "widgets" / "contactos" / "manifest.json")
                          .read_text(encoding="utf-8"))
    return (manifest.get("collections") or {}).get("groups") or {}


@F1
def test_an_empty_group_is_made_by_its_name_and_has_an_id(directory_world):
    cd, _d, _rows = directory_world
    col = _groups_collection()
    assert col and (col.get("via") or {}).get("put"), "the contacts manifest declares a `groups` collection"
    made = cd.apply_action(col["via"]["put"], {"name": GROUP_ES})
    assert made.get("ok") is True
    gid = str((made.get("result") or {}).get(col.get("id") or "id") or "")
    assert gid and gid != GROUP_ES, "a group's id is not its label"


@F1
def test_a_renamed_group_keeps_its_members(directory_world):
    cd, _d, _rows = directory_world
    col = _groups_collection()
    made = cd.apply_action(col["via"]["put"], {"name": GROUP_ES, "members": list(PARENTS)})
    gid = (made.get("result") or {}).get(col.get("id") or "id")
    assert cd.apply_action(col["via"]["patch"], {col.get("id") or "id": gid, "name": "Padres 3ºB"}).get("ok") is True
    assert _rail(cd).get("Padres 3ºB") == 3 and GROUP_ES not in _rail(cd)


# ── mirrored to WhatsApp, then written to ────────────────────────────────────────────────────────────────────────

def _mirror(members: list[str], name: str = "Grupo de demostración") -> dict:
    from widgets.mensajeria import data as ms
    return ms.apply_action("create_group", {"platform": "whatsapp", "name": name, "members": members})


def test_the_group_is_mirrored_to_whatsapp_with_each_members_own_chat(directory_world):
    cd, _d, rows = directory_world
    names = [_row(cd, cid)["name"] for cid in PARENTS]
    made = _mirror(names)
    assert made["ok"] is True and made["result"]["members"] == names, made
    from widgets.mensajeria import data as ms
    order = ms.load_db()["pending_group"][-1]
    chats = {m["contactId"]: m["chatId"] or m["to"] for m in order["members"]}
    lids = {cid: _row(cd, cid)["channels"][0]["chatId"] for cid in PARENTS}
    assert order["platform"] == "whatsapp" and chats == lids, "each member by the chat she really has (a @lid)"


def test_a_mirror_with_an_unreachable_member_creates_nothing(directory_world):
    cd, _d, _rows = directory_world
    made = _mirror([_row(cd, "lucia-active")["name"], "Tomeu Bauzà"])
    from widgets.mensajeria import data as ms
    assert made["ok"] is False and not ms.load_db().get("pending_group"), made


@pytest.mark.xfail(strict=True, reason="V2-854 gap: create_group re-resolves member NAMES; a contacts group's "
                                       "members are contact ids, and a namesake makes the mirror refuse")
def test_the_group_is_mirrored_from_its_members_ids(directory_world):
    _cd, _d, _rows = directory_world
    made = _mirror(["raquel-1", "jordi-1", "lucia-3"])          # Raquel Soto, Jordi Puig, Lucia Coll — by id
    assert made["ok"] is True and len(made["result"]["members"]) == 3, made


@pytest.mark.parametrize("said", ["Grupo de demostración", "grupo de demostracion"], ids=["typed", "voice"])
def test_a_message_to_the_mirrored_group_goes_to_the_group(directory_world, said):
    """The connector hands the new group back as a chat; the directory takes it in as a `kind: group` row (the same
    door every import uses) — and the group is then ONE recipient, never its members one by one."""
    cd, _d, _rows = directory_world
    from widgets.contactos import imports
    members = [{"name": _row(cd, cid)["name"], "channels": [dict(_row(cd, cid)["channels"][0])]} for cid in PARENTS]
    db = cd.load_db()
    imports.absorb(db, {"groups": [{"name": "Grupo de demostración", "platform": "whatsapp", "members": members,
                                    "channels": [{"platform": "whatsapp", "chatId": "120363000000099999@g.us"}]}]},
                   source="whatsapp")
    cd.store.save(cd.WIDGET_ID, db)
    group = next(c for c in cd.load_db()["contacts"] if c["name"] == "Grupo de demostración")
    assert group["kind"] == "group" and sorted(group["members"]) == sorted(PARENTS), "one row per person, reused"
    from widgets.mensajeria.outbound import targets
    t = targets.resolve_target({"contact": said, "text": "Reunión el jueves a las 18:00"})
    assert t.get("ok") and t.get("contactId") == group["id"] and t.get("chatId") == "120363000000099999@g.us", t
