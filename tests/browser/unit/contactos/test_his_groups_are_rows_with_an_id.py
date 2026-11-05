"""V2-854 F1 · his directory's storage: groups as rows with an id, linked agents, the unclassified, where a word came from.

Measured on his engine (2026-11-05): 2,883 entries, group labels unused, two favorites, no relation — the group a
person is in was a free string with no identity, so nothing could name, rename or delete «the parents of the
school». The rules (`widgets/contactos/groups.py`, `model.py`):

  · a group is a ROW of the `groups` collection (`groupId`, `name`, `native`); the natives (favorites, family,
    friends, colleagues) are DECLARED in the manifest and seeded; every label a contact carries becomes a group of
    his — idempotently, on every read; a contact may be in several;
  · membership has one owner per group — the contact's labels, and `favorite` for the native favorites;
  · create / rename / delete / add / remove members; a native is never renamed or deleted; deleting a group keeps
    its contacts;
  · `agents: [{agent_id, cluster, label}]` on a person or a company only;
  · «unclassified» (no phone, no e-mail, no channel) is DERIVED, never stored;
  · a word he uses for a person carries where it came from: «learned» from his pick, else his — and a word he sets
    again by hand is his.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store and workspace — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets.contactos import data as d
    db = d.load_db()
    db["contacts"] += [
        {"id": "p1", "kind": "person", "name": "Laia Puig", "phone": "+34 600 000 001", "groups": ["Padres cole"]},
        {"id": "p2", "kind": "person", "name": "Jordi Roca", "email": "jordi@example.org",
         "groups": ["Padres cole", "Guitarra"]},
        {"id": "p3", "kind": "person", "name": "Sam Lee", "channels": [{"platform": "telegram", "chatId": "77"}]},
        {"id": "p4", "kind": "person", "name": "Nadie Sin Datos"},
        {"id": "k1", "kind": "company", "name": "Acme Robots", "phone": "915550000"},
        {"id": "s1", "kind": "place", "name": "Casa Lucio", "phone": "913650000"},
    ]
    d.store.save(d.WIDGET_ID, db)
    return d


def _rows(d):
    return {r["name"]: r for r in d.view_data()["groupRows"]}


def _c(d, cid):
    return next(c for c in d.load_db()["contacts"] if c["id"] == cid)


# ── groups are rows ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_natives_are_declared_seeded_and_ranked_first(ct):
    from widgets.contactos import groups
    assert groups.native_ids() == ["favorites", "family", "friends", "colleagues"], "declared in the manifest"
    rows = ct.view_data()["groupRows"]
    assert [r["groupId"] for r in rows[:4]] == groups.native_ids() and all(r["native"] for r in rows[:4])


def test_his_labels_become_groups_of_his_once(ct):
    first = {n: r["groupId"] for n, r in _rows(ct).items()}
    assert {"Padres cole", "Guitarra"} <= set(first) and not _rows(ct)["Guitarra"]["native"]
    db = ct.load_db()
    ct.store.save(ct.WIDGET_ID, db)
    assert {n: r["groupId"] for n, r in _rows(ct).items()} == first, "idempotent: the same ids on every read"
    assert len(ct.load_db()["groups"]) == len(first), "never a second row for one label"
    assert _rows(ct)["Padres cole"]["count"] == 2


def test_a_contact_is_in_several_groups(ct):
    from widgets.contactos import groups
    db = ct.load_db()
    ids = groups.ids_of(db, _c(ct, "p2"))
    assert {_rows(ct)["Padres cole"]["groupId"], _rows(ct)["Guitarra"]["groupId"]} == set(ids)


def test_the_migration_seeds_the_rows_of_an_old_store(ct):
    from widgets.contactos import data as d
    db = {"contacts": [{"id": "x", "name": "A", "groups": ["Vecinos"]}], "next_id": 2}
    out = d._migrate(db, 3)
    assert "Vecinos" in {r["name"] for r in out["groups"]} and "family" in {r["groupId"] for r in out["groups"]}


def test_create_with_members_rename_and_delete_keep_the_people(ct):
    r = ct.apply_action("create_group", {"name": "Padres del colegio", "contactIds": ["p1", "p3"]})
    gid = r["result"]["group"]["groupId"]
    assert r["ok"] and r["result"]["created"] and r["result"]["group"]["members"] == 2
    again = ct.apply_action("create_group", {"name": "padres del colegio"})
    assert again["result"]["group"]["groupId"] == gid and not again["result"]["created"], "one name, one group"
    ct.apply_action("rename_group", {"groupId": gid, "name": "Cole de los niños"})
    assert "Cole de los niños" in _c(ct, "p3")["groups"] and _rows(ct)["Cole de los niños"]["groupId"] == gid
    out = ct.apply_action("delete_group", {"groupId": gid})
    assert out["ok"] and out["result"]["members_kept"] == 2
    assert "Cole de los niños" not in _rows(ct) and _c(ct, "p3")["name"] == "Sam Lee", "the people stay"
    assert "Cole de los niños" not in _c(ct, "p1")["groups"]


def test_members_go_in_and_out_and_favorites_is_the_favorite_field(ct):
    ct.apply_action("add_to_group", {"groupId": "friends", "contactIds": ["p1", "p2"]})
    assert _rows(ct)["friends"]["count"] == 2
    ct.apply_action("add_to_group", {"group": "friends", "contactId": "p1", "remove": True})
    assert _rows(ct)["friends"]["count"] == 1 and "friends" not in _c(ct, "p1")["groups"]
    ct.apply_action("add_to_group", {"groupId": "favorites", "contactId": "p3"})
    assert _c(ct, "p3")["favorite"] is True and "favorites" not in (_c(ct, "p3").get("groups") or [])
    ct.apply_action("set_favorite", {"contactId": "p4"})
    assert _rows(ct)["favorites"]["count"] == 2, "the ★ and the group are one membership"


def test_a_native_is_never_renamed_or_deleted(ct):
    assert ct.apply_action("rename_group", {"groupId": "family", "name": "Familia"})["ok"] is False
    assert ct.apply_action("delete_group", {"groupId": "favorites"})["ok"] is False
    assert ct.apply_action("add_to_group", {"groupId": "nope", "contactId": "p1"})["ok"] is False


def test_the_groups_are_a_collection_a_door_can_read(ct):
    from widgets import rows
    assert rows.spec("contactos", "groups")["id"] == "groupId"
    ct.load_db()                         # any read of the directory writes the rows a new label needs
    assert {"family", "Guitarra"} <= {r["name"] for r in rows._rows("contactos", "groups")}


# ── the record ───────────────────────────────────────────────────────────────────────────────────────────────

def test_a_person_or_a_company_links_agents_nothing_else_does(ct):
    r = ct.apply_action("set_agent", {"contactId": "k1", "agent_id": "acme-bot", "cluster": "acme"})
    assert r["ok"] and _c(ct, "k1")["agents"] == [{"agent_id": "acme-bot", "cluster": "acme", "label": ""}]
    ct.apply_action("set_agent", {"contactId": "k1", "agent_id": "acme-bot", "cluster": "acme"})
    assert len(_c(ct, "k1")["agents"]) == 1, "one link per agent and cluster"
    ct.apply_action("set_agent", {"contactId": "p1", "agent_id": "laia-agent"})
    assert _c(ct, "p1")["agents"][0]["agent_id"] == "laia-agent"
    assert ct.apply_action("set_agent", {"contactId": "s1", "agent_id": "x"})["ok"] is False
    ct.apply_action("set_agent", {"contactId": "k1", "agent_id": "acme-bot", "cluster": "acme", "remove": True})
    assert "agents" not in _c(ct, "k1")


def test_unclassified_is_derived_never_stored(ct):
    from widgets.contactos import model
    assert [c["id"] for c in ct.load_db()["contacts"] if model.unclassified(c)] == ["p4"]
    assert "unclassified" not in _c(ct, "p4") and ct.view_data()["unclassified_count"] == 1
    ct.apply_action("add_email", {"contactId": "p4", "email": "nadie@example.org"})
    assert not model.unclassified(_c(ct, "p4")) and ct.view_data()["unclassified_count"] == 0


def test_a_word_carries_where_it_came_from(ct):
    ct.apply_action("set_alias", {"contactId": "p2", "alias": "Jordy", "source": "learned"})
    from widgets.contactos import model
    assert model.alias_source(_c(ct, "p2"), "Jordy") == "learned"
    ct.apply_action("set_alias", {"contactId": "p2", "alias": "Jordy"})
    assert model.alias_source(_c(ct, "p2"), "Jordy") == "his", "set again by hand, it is his"
    assert _c(ct, "p2")["aliases"] == ["Jordy"]
    ct.apply_action("set_alias", {"contactId": "p2", "alias": "Jordy", "remove": True})
    assert not _c(ct, "p2").get("aliasSources")
