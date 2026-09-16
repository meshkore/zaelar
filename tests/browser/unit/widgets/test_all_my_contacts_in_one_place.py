"""V2-714 · Every contact in one place: import-only, hideable, and groups are a kind.

## The session

`c20123ab`, 2026-09-16. He tried to write to somebody on Telegram and could not:

    i=344/351  «I wanna write to my contact Ivan. In Telegram.»
    i=436      zaelar «Ivan does exist in your contacts, and his email is ivan@citingart.com…»
    i=441      «This is not my Ivan.»   i=483 «My Ivan is called Ivan Mushikin. And I got him in my
                                               Telegram contacts.»
    i=1020     «We didn't have that. I just see Google and Apple and another one. But no WhatsApp or
                Telegram.»

And his rules, given afterwards:

> «Hacemos solo import. Idealmente import continuo. En local los contactos son editables y se pueden
> ocultar, se quedan mapeados a las plataformas, pero ya no se modifican más desde el conector.»
> «Debemos soportar grupos… combinamos grupos de cada plataforma, y los combinamos con los clusters de
> MeshKore, que también son grupos pero de agentes.»

## What this file pins

1. the PHONE is what makes one person out of three address books — the key that actually unifies them;
2. an import never overwrites what he wrote, and the two ADDITIONS it may still make;
3. hiding keeps the mapping, which is the whole reason it beats deleting;
4. a group is a KIND with members, not a label — the confusion `data.py` has warned about since V2-523;
5. one source can serve two families, which is what puts Telegram in the contacts card at all.
"""
from __future__ import annotations

import copy

import pytest

from connectors import registry
from widgets import store
from widgets.contactos import data, imports

BASE = {
    "contacts": [
        {"id": "c1", "kind": "person", "name": "Iván Mushkin", "city": "", "phone": "+34 600 11 22 33",
         "email": "ivan@citingart.com", "notes": "el del taller", "groups": [], "favorite": False,
         "channels": [], "preferred": "", "parentId": "", "created": "2026-01-01", "updated": "2026-01-01",
         "source": "google", "googleId": "g1", "externalIds": {"google": "g1"}},
        {"id": "c2", "kind": "person", "name": "Marta Ruiz", "city": "Soria", "phone": "", "email": "",
         "notes": "", "groups": [], "favorite": False, "channels": [], "preferred": "", "parentId": "",
         "created": "2026-01-01", "updated": "2026-01-01", "source": "google", "externalIds": {}},
    ],
    "next_id": 3,
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save("contactos", copy.deepcopy(BASE))
    yield


def _db():
    return copy.deepcopy(BASE)


# ── 1 · the phone is the key that unifies three address books ───────────────────────────────────────────

@pytest.mark.parametrize("spelling", ["+34600112233", "600 11 22 33", "0034600112233", "+34-600-112-233"])
def test_the_same_number_written_four_ways_is_one_account(spelling):
    assert imports.phone_key(spelling) == imports.phone_key("+34 600 11 22 33")


def test_a_number_too_short_to_be_an_account_matches_NOTHING():
    """«, which never matches anything rather than matching everything.» An extension or a short code is
    not an identity, and a loose key here folds two strangers into one person he cannot un-merge."""
    assert imports.phone_key("1234") == ""
    assert imports.phone_key("") == ""
    db = _db()
    imports.merge_contacts(db, [{"name": "Centralita", "phone": "1234",
                                 "externalIds": {"telegram": "t9"}}], source="telegram")
    assert len(db["contacts"]) == 3, "it must have been added as somebody NEW, not folded into a stranger"


def test_his_telegram_ivan_and_his_google_ivan_are_ONE_person():
    """The measured failure, from the other side. Google knew an Iván with an email; Telegram knows an Iván
    with a username and the same phone. Two rows is what made the card answer «this is not my Ivan»."""
    db = _db()
    res = imports.merge_contacts(db, [{
        "name": "Ivan Mushikin", "phone": "+34600112233",
        "channels": [{"platform": "telegram", "handle": "@mushikin", "chatId": "777"}],
        "externalIds": {"telegram": "777"}}], source="telegram")
    assert res["added"] == 0 and res["filled"] == 1, "one person, not two"
    c = db["contacts"][0]
    assert c["name"] == "Iván Mushkin", "HIS spelling wins — an import never renames what he typed"
    assert c["externalIds"] == {"google": "g1", "telegram": "777"}
    assert any(ch["platform"] == "telegram" and ch["handle"] == "@mushikin" for ch in c["channels"]), \
        "…and now «write to Iván on Telegram» has somewhere to go, which is the whole point"


def test_the_external_id_survives_him_renaming_the_person():
    db = _db()
    imports.merge_contacts(db, [{"name": "X", "externalIds": {"telegram": "777"}}], source="telegram")
    db["contacts"][-1]["name"] = "Como yo le llamo"
    res = imports.merge_contacts(db, [{"name": "X", "externalIds": {"telegram": "777"}}], source="telegram")
    assert res["added"] == 0


# ── 2 · import-only: it fills blanks, and it adds ways to reach him ─────────────────────────────────────

def test_an_import_NEVER_overwrites_what_he_wrote():
    """His rule, and the reason there is no `authoritative` flag anywhere in `imports.py`: «ya no se
    modifican más desde el conector»."""
    db = _db()
    imports.merge_contacts(db, [{"name": "OTRO NOMBRE", "phone": "+34600112233",
                                 "email": "otro@sitio.com", "notes": "otra nota",
                                 "externalIds": {"telegram": "777"}}], source="telegram")
    c = db["contacts"][0]
    assert (c["name"], c["email"], c["notes"]) == ("Iván Mushkin", "ivan@citingart.com", "el del taller")


def test_it_DOES_fill_a_blank():
    db = _db()
    imports.merge_contacts(db, [{"name": "Marta Ruiz", "city": "Soria", "phone": "+34611000111",
                                 "externalIds": {"whatsapp": "w1"}}], source="whatsapp")
    assert db["contacts"][1]["phone"] == "+34611000111", "empty is not «his», it is missing"


def test_a_NEW_channel_is_an_addition_not_a_modification():
    """The one exception he was asked to confirm: without it, «escríbele a Iván por Telegram» stops working
    the month Iván opens a Telegram account, which is exactly what this batch exists to fix."""
    db = _db()
    imports.merge_contacts(db, [{"name": "Iván", "externalIds": {"google": "g1"},
                                 "channels": [{"platform": "whatsapp", "handle": "+34600112233"}]}],
                           source="whatsapp")
    assert [ch["platform"] for ch in db["contacts"][0]["channels"]] == ["whatsapp"]


def test_a_second_pass_changes_nothing():
    """Continuous import is continuous DISCOVERY. A pass that brings the same rows must be a no-op, or the
    ledger would churn `updated` on every tick and every row would look freshly edited."""
    db = _db()
    rows = [{"name": "Nuevo", "phone": "+34699888777", "externalIds": {"telegram": "t1"}}]
    first = imports.merge_contacts(db, rows, source="telegram")
    second = imports.merge_contacts(db, rows, source="telegram")
    assert first["added"] == 1 and second == {"added": 0, "filled": 0, "unchanged": 1, "read": 1}


# ── 3 · hiding keeps the mapping, which is why it beats deleting ────────────────────────────────────────

def test_a_hidden_contact_is_not_resurrected_by_the_next_pass():
    """THE reason hiding exists. Neither platform has an address-book write API, so deleting is local — and
    a deleted row has no mapping left, so the next import brings the person straight back."""
    db = _db()
    rows = [{"name": "Spam Bot", "externalIds": {"telegram": "t42"}}]
    imports.merge_contacts(db, rows, source="telegram")
    hid = db["contacts"][-1]
    hid["hidden"] = True
    res = imports.merge_contacts(db, rows, source="telegram")
    assert res["added"] == 0, "it matched the hidden row instead of adding a second one"
    assert hid["hidden"] is True, "and an import never un-hides what he took off his screen"


def test_hidden_rows_leave_every_surface_at_once():
    """One reader (`data.visible`), because «hidden» has to mean the same thing in the card, in the digest
    and in the voice index — a row that is invisible in one and offerable in another is worse than both."""
    db = data.load_db()
    db["contacts"][0]["hidden"] = True
    store.save("contactos", db)
    assert data.view_data()["count"] == 1
    assert data.view_data()["hidden_count"] == 1
    assert not any("Mushkin" in r["label"] for r in data.ref_index())
    assert "Mushkin" not in data.prompt_digest()


def test_hide_and_unhide_through_the_declared_action():
    out = data.apply_action("hide_contact", {"contactId": "c1"})
    assert out["ok"] and out["result"]["hidden"] is True and out["count"] == 1
    out = data.apply_action("hide_contact", {"contactId": "c1", "hidden": False})
    assert out["ok"] and out["result"]["hidden"] is False and out["count"] == 2


# ── 4 · a group is a KIND with members, never a label ───────────────────────────────────────────────────

GROUP = {"name": "Familia", "platform": "telegram", "subtype": "group",
         "externalIds": {"telegram": "-100"},
         "channels": [{"platform": "telegram", "chatId": "-100"}],
         "members": [{"name": "Iván Mushkin", "phone": "+34600112233",
                      "externalIds": {"telegram": "777"}},
                     {"name": "Lucía Pons", "externalIds": {"telegram": "778"}}]}


def test_a_group_arrives_as_a_row_with_members_and_a_channel():
    db = _db()
    imports.merge_groups(db, [copy.deepcopy(GROUP)], source="telegram")
    g = next(c for c in db["contacts"] if c.get("kind") == "group")
    assert g["platform"] == "telegram" and g["subtype"] == "group"
    assert any(ch["platform"] == "telegram" for ch in g["channels"]), \
        "you can WRITE to a group — that is what makes it a row and not a tag"
    assert len(g["members"]) == 2


def test_a_member_is_merged_as_a_PERSON_first():
    """Members go through the same keys as everybody else, so the Iván already in his Google contacts is
    the Iván in the group — not a third row."""
    db = _db()
    imports.merge_groups(db, [copy.deepcopy(GROUP)], source="telegram")
    ivans = [c for c in db["contacts"] if "Mushkin" in c["name"]]
    assert len(ivans) == 1
    g = next(c for c in db["contacts"] if c.get("kind") == "group")
    assert ivans[0]["id"] in g["members"]


def test_a_LABEL_is_still_a_label():
    """`data.py:66` has warned since V2-523: a kind says what the entry IS, a label says how he files it.
    Folding a group chat into the label field would be exactly that confusion."""
    db = data.load_db()
    data.apply_action("add_contact", {"name": "Pepe", "group": "amigos del trabajo"})
    d = data.view_data()
    assert any(g["id"] == "amigos del trabajo" for g in d["groups"]), "labels ride the `groups` rail"
    assert d["circles"] == [], "…and no group chat appeared out of a label"


def test_somebody_joining_is_new_information_not_an_edit():
    db = _db()
    imports.merge_groups(db, [copy.deepcopy(GROUP)], source="telegram")
    bigger = copy.deepcopy(GROUP)
    bigger["members"].append({"name": "Nuevo Miembro", "externalIds": {"telegram": "779"}})
    bigger["name"] = "Familia RENOMBRADA EN TELEGRAM"
    imports.merge_groups(db, [bigger], source="telegram")
    g = next(c for c in db["contacts"] if c.get("kind") == "group")
    assert len(g["members"]) == 3
    assert g["name"] == "Familia", "the name is a field — an import does not rename what he can see"


def test_a_broadcast_channel_says_its_members_CANNOT_be_listed():
    """An empty list that means «we cannot know» must never look like one that means «nobody»."""
    db = _db()
    imports.merge_groups(db, [{"name": "Canal de noticias", "platform": "telegram", "subtype": "channel",
                               "externalIds": {"telegram": "-200"}, "members": []}], source="telegram")
    g = next(c for c in db["contacts"] if c.get("kind") == "group")
    assert g["membersKnown"] is False


def test_removing_a_person_does_not_leave_them_in_a_group():
    """The same rule `remove_contact` already had for `parentId`, one relation over: a stale id paints a
    member count nobody can open."""
    db = data.load_db()
    imports.merge_groups(db, [copy.deepcopy(GROUP)], source="telegram")
    store.save("contactos", db)
    gid = next(c["id"] for c in db["contacts"] if c.get("kind") == "group")
    victim = next(c["id"] for c in db["contacts"] if "Mushkin" in c["name"])
    data.apply_action("remove_contact", {"contactId": victim})
    after = next(c for c in data.load_db()["contacts"] if c["id"] == gid)
    assert victim not in after["members"]


def test_a_cluster_is_a_group_of_AGENTS():
    from widgets.contactos import sources
    db = _db()
    imports.merge_groups(db, [{"name": "commons", "platform": "meshkore", "subtype": "cluster",
                               "externalIds": {"meshkore": "c_abc"},
                               "channels": [{"platform": "meshkore", "handle": "commons"}],
                               "members": [{"name": "dev-main", "kind": "agent",
                                            "externalIds": {"meshkore": "c_abc/dev-main"},
                                            "channels": [{"platform": "meshkore",
                                                          "handle": "commons/dev-main"}]}]}],
                          source="meshkore")
    agent = next(c for c in db["contacts"] if c["name"] == "dev-main")
    assert agent["kind"] == "agent", "an agent is not a person and must never be filed as one"
    assert "meshkore" in sources.KNOWN


def test_the_members_view_refuses_a_non_group():
    out = data.apply_action("show_contact_members", {"contactId": "c1"})
    assert not out["ok"] and "grupo" in out["error"]


# ── 5 · one source, two families ────────────────────────────────────────────────────────────────────────

def test_telegram_and_whatsapp_are_contact_sources_TOO():
    """What he actually saw: «I just see Google and Apple and another one. But no WhatsApp or Telegram.»
    The strip filtered on `family == "contactos"` and those two are `mensajeria`."""
    rows = {d["id"]: d for d in registry.descriptors()}
    for wid in ("telegram", "whatsapp"):
        assert rows[wid]["family"] == "mensajeria", "they have not stopped being message connectors"
        assert registry.serves(rows[wid], "contactos") and registry.serves(rows[wid], "mensajeria")


def test_a_source_that_declares_nothing_keeps_its_one_family():
    rows = {d["id"]: d for d in registry.descriptors()}
    g = rows["google-contacts"]
    assert g["families"] == ["contactos"] and not registry.serves(g, "mensajeria")


def test_the_card_shows_them_with_their_REAL_state(monkeypatch):
    """The disarm of `serves` came back green and accused this test: listing Telegram is not the property —
    `_SOURCES` names it either way. The property is the STATUS. Filtering on `family == "contactos"` leaves
    a CONNECTED Telegram reading «unavailable», and that strip's own docstring is about exactly this
    distinction: «no lo has enlazado» and «no lo hemos construido» are different sentences.

    Built on a fake registry so it measures the reader and not whether his phone is linked right now."""
    from widgets.contactos import gcontacts
    monkeypatch.setattr(gcontacts, "_SOURCES", (("google-contacts", "Google Contacts"),
                                                ("telegram", "Telegram"), ("whatsapp", "WhatsApp")))
    monkeypatch.setattr(registry, "descriptors", lambda: [
        {"id": "google-contacts", "family": "contactos", "families": ["contactos"],
         "label": "Google Contacts", "connected": True, "status": "connected"},
        {"id": "telegram", "family": "mensajeria", "families": ["mensajeria", "contactos"],
         "label": "Telegram", "connected": True, "status": "connected"},
        {"id": "whatsapp", "family": "mensajeria", "families": ["mensajeria", "contactos"],
         "label": "WhatsApp", "connected": False, "status": "off"},
    ])
    strip = {p["id"]: p for p in gcontacts.providers()}
    assert strip["telegram"]["status"] == "connected", "a linked source must not read as «not built»"
    assert strip["whatsapp"]["status"] == "off", "…and an unlinked one must not read as «not built» either"
    assert strip["telegram"].get("imports") is True and "sync" in strip["telegram"]
    assert strip["google-contacts"].get("imports") is not True, \
        "Google has a two-way SYNC, not an import switch — two different contracts, two different boxes"


def test_the_widget_declares_the_icons_and_one_switch():
    import pathlib
    js = (pathlib.Path(__file__).resolve().parents[4] / "widgets/contactos/widget.js").read_text()
    assert "telegram:" in js and "whatsapp:" in js and "meshkore:" in js, "the icons he asked for"
    assert "IMPORT_SOURCES" in js and "renderImportBox" in js
    assert js.count("set_auto") >= 1, "ONE switch — «no vamos a poner dos opciones»"


# ── 6 · the filters those rows make answerable ──────────────────────────────────────────────────────────

def test_show_view_answers_my_groups_and_my_telegram_contacts():
    db = data.load_db()
    imports.merge_groups(db, [copy.deepcopy(GROUP)], source="telegram")
    store.save("contactos", db)
    assert data.apply_action("show_view", {"kind": "group"})["result"]["count"] == 1
    assert data.apply_action("show_view", {"source": "telegram"})["result"]["count"] >= 2
    assert data.apply_action("show_view", {"source": "google"})["result"]["count"] == 2
