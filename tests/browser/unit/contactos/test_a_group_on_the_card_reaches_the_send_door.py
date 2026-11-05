"""V2-854 F5 · what the contacts card needs from the store for his groups, and how a message to one LEAVES.

  · a relation puts the person in the native group that declares it («partner» → family) — derived on every read,
    never a label, so the relation stays the one owner: a label toggle cannot take her out while it says partner;
  · a group of his is mirrored on WhatsApp by the chat group of the same name the import brought (derived, never a
    stored pointer), and the card is told so in `groupRows[].mirror`;
  · «send a message to this group» from the card is never sent from the card: `message_group` writes HIS order from
    the voice pack and hands it to the conversation (the `POST /api/chat` door), so the send meets the same message
    door, consent and channel resolution as a spoken one. With no mirror the card must say how (create it, or one by
    one); only his click reaches it (`internal`, `worker: false`, provenance «user»);
  · the voice can push the same views the rail shows: one of his groups by id, and the unclassified.
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
        {"id": "p1", "kind": "person", "name": "Ona Vidal", "relation": "partner",
         "channels": [{"platform": "whatsapp", "chatId": "100@lid"}]},
        {"id": "p2", "kind": "person", "name": "Pau Serra", "groups": ["School parents"],
         "channels": [{"platform": "whatsapp", "chatId": "200@lid"}]},
        {"id": "p3", "kind": "person", "name": "Mia Font", "groups": ["School parents"],
         "channels": [{"platform": "telegram", "chatId": "300"}]},
        {"id": "p4", "kind": "person", "name": "Leo Pons", "groups": ["School parents", "Climbing"]},
        {"id": "w1", "kind": "group", "name": "Climbing", "platform": "whatsapp",
         "channels": [{"platform": "whatsapp", "chatId": "999@g.us"}]},
    ]
    d.store.save(d.WIDGET_ID, db)
    return d


@pytest.fixture
def handed(monkeypatch):
    """The conversation door, recorded: what the card would hand to the live session. And the click is his."""
    from widgets import provenance
    from widgets.contactos import group_actions
    got: list[str] = []
    monkeypatch.setattr(group_actions, "_hand_over", lambda order: got.append(order) or "")
    provenance.note("contactos", "user")
    return got


def _row(d, name):
    return next(r for r in d.view_data()["groupRows"] if r["name"] == name)


def _act(d, action, **payload):
    db = d.load_db()
    return d.ACTIONS[action](action, payload, "", db, d.visible(db), "2026-11-05")


# ── decision 2: a relation files the person in its native group ─────────────────────────────────────────────

def test_a_relation_puts_the_person_in_its_native_group(ct):
    from widgets.contactos import groups
    db = ct.load_db()
    fam = groups.find(db, "family")
    ona = next(c for c in db["contacts"] if c["id"] == "p1")
    assert groups.is_member(fam, ona) and groups.by_relation(fam, ona), "partner → family, by the declaration"
    assert "family" not in [g.lower() for g in ona.get("groups") or []], "derived, never written as a label"
    assert _row(ct, "family")["count"] == 1
    assert "family" in groups.ids_of(db, ona)


def test_the_relation_stays_the_owner_of_that_membership(ct):
    from widgets.contactos import groups
    db = ct.load_db()
    fam = groups.find(db, "family")
    ona = next(c for c in db["contacts"] if c["id"] == "p1")
    assert groups.set_member(fam, ona, False) is False, "a label cannot contradict who she is to him"
    assert groups.is_member(fam, ona)
    ona["relation"] = "friend"
    assert not groups.is_member(fam, ona) and groups.is_member(groups.find(db, "friends"), ona)


# ── the WhatsApp mirror, derived ────────────────────────────────────────────────────────────────────────────

def test_the_whatsapp_chat_group_of_the_same_name_is_the_mirror(ct):
    assert _row(ct, "Climbing")["mirror"]["contactId"] == "w1"
    assert "mirror" not in _row(ct, "School parents")


# ── a message to a group goes to the conversation, never out of the card ───────────────────────────────────

def test_a_group_with_a_mirror_is_written_to_there(ct, handed):
    res = _act(ct, "message_group", groupId=_row(ct, "Climbing")["groupId"], text="training at 7")
    assert res["ok"] and res["result"]["mode"] == "group"
    assert len(handed) == 1 and "Climbing" in handed[0] and "training at 7" in handed[0]


def test_a_group_without_a_mirror_needs_him_to_say_how(ct, handed):
    gid = _row(ct, "School parents")["groupId"]
    res = _act(ct, "message_group", groupId=gid, text="no school on friday")
    assert res["ok"] is False and res["needs"] == "mode" and not handed, "it asks; nothing is handed over"


def test_one_by_one_names_every_member_he_can_reach(ct, handed):
    gid = _row(ct, "School parents")["groupId"]
    res = _act(ct, "message_group", groupId=gid, text="no school on friday", mode="each")
    assert res["ok"], res
    order = handed[0]
    assert "Pau Serra" in order and "Mia Font" in order and "no school on friday" in order
    assert "Leo Pons" not in order and res["result"]["left_out"] == ["Leo Pons"], "no channel → named back"


def test_creating_the_mirror_names_only_who_is_on_whatsapp(ct, handed):
    gid = _row(ct, "School parents")["groupId"]
    res = _act(ct, "message_group", groupId=gid, mode="mirror")
    assert res["ok"], res
    assert "Pau Serra" in handed[0] and "Mia Font" not in handed[0] and "School parents" in handed[0]


def test_the_order_is_written_in_the_agents_language(ct, handed, monkeypatch):
    from i18n import langs
    gid = _row(ct, "Climbing")["groupId"]
    for code, word in (("es", "Manda"), ("en", "Send")):
        monkeypatch.setattr(langs, "current_code", lambda c=code: c)
        handed.clear()
        assert _act(ct, "message_group", groupId=gid, text="hola")["ok"]
        assert handed[0].startswith(word), handed[0]


def test_only_his_click_reaches_it(ct, handed):
    from widgets import provenance
    provenance.note("contactos", "flash")
    res = _act(ct, "message_group", groupId=_row(ct, "Climbing")["groupId"], text="x")
    assert res["ok"] is False and not handed
    from widgets import runtime
    spec = (runtime.get("contactos") or {})["actions"]["message_group"]
    assert spec.get("internal") is True and spec.get("worker") is False, "never offered to the model or a worker"


def test_no_live_session_says_so(ct, monkeypatch):
    from widgets import provenance
    from voice import screens
    provenance.note("contactos", "user")
    monkeypatch.setattr(screens, "has_session", lambda: False)
    res = _act(ct, "message_group", groupId=_row(ct, "Climbing")["groupId"], text="x")
    assert res["ok"] is False and res["reason"] == "no_session"


# ── the voice pushes the views the rail shows ──────────────────────────────────────────────────────────────

def test_the_voice_can_show_one_of_his_groups_and_the_unclassified(ct):
    gid = _row(ct, "School parents")["groupId"]
    res = _act(ct, "show_view", groupId=gid)
    assert {m["id"] for m in res["result"]["matches"]} == {"p2", "p3", "p4"}
    assert ct.load_db()["view"]["sel"]["groupId"] == gid
    res = _act(ct, "show_view", unclassified=True)
    assert {m["id"] for m in res["result"]["matches"]} == {"p4"}


def test_the_card_is_handed_what_its_selectors_offer(ct):
    v = ct.view_data()
    assert "partner" in v["relations"] and v["native_groups"][1]["id"] == "family"
