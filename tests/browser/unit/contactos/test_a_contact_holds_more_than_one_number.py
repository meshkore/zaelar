"""V2-715 — a directory entry is not one phone number, and a platform tab is a filter.

The operator, 2026-09-17, redesigning the directory: «piensa que podemos tener restaurantes, que estos
restaurantes pueden ser favoritos o no, o que podemos tener a cuatro personas que estén vinculadas a la
misma empresa, o varios teléfonos que estén vinculados a la misma empresa. Es decir, tiene que ser potente
el widget de contactos y su modelo de datos.» And, about the source icons: «cuando entramos en Telegram
quiero ver solo los contactos de Telegram».

MEASURED before writing any of it: the record held ONE `phone` and ONE `email`, and
`connectors/contacts/google_people.py::_primary` threw the rest of Google's numbers away on the way in —
so a company with a switchboard, a mobile and a fax arrived as one number and the other two did not exist
on this side of the sync.

The rule that makes the change safe is in `widgets/contactos/model.py::normalize`: the LIST is the truth
and `phone`/`email` are its head, kept in step in both directions. Four modules outside this widget read
the scalar (`widgets/directory.py` resolves a spoken number with it), and a list that silently replaced it
would have made every one of them read an empty field on a contact that holds three numbers.
"""
from __future__ import annotations

import pytest

from widgets import store
from widgets.contactos import data as d
from widgets.contactos import model


@pytest.fixture()
def ct(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    return d


def _add(ct, **payload):
    r = ct.apply_action("add_contact", {**payload, "q": ""})
    assert r.get("ok"), r
    return r["result"]["contact"]["id"]


# ── the shape ───────────────────────────────────────────────────────────────────────────────────────────

def test_the_scalar_and_the_list_are_kept_in_step_in_BOTH_directions():
    c = {"phone": "600 111 222", "email": "a@b.c"}
    model.normalize(c)
    assert c["phones"] == [{"value": "600 111 222", "label": ""}]
    assert c["emails"] == [{"value": "a@b.c", "label": ""}]
    c2 = {"phones": [{"value": "915550000", "label": "centralita"}]}
    model.normalize(c2)
    assert c2["phone"] == "915550000", "every reader outside this widget still reads the scalar"


def test_a_primary_the_operator_typed_goes_in_FRONT_instead_of_being_dropped():
    """He edits the scalar to a number the list does not hold: that is a new primary, not a mistake."""
    c = {"phone": "600 000 000", "phones": [{"value": "915550000", "label": "centralita"}]}
    model.normalize(c)
    assert [r["value"] for r in c["phones"]] == ["600 000 000", "915550000"]


def test_the_same_number_written_twice_is_ONE_number(ct):
    cid = _add(ct, name="Telefónica", kind="empresa", phone="+34 91 555 00 00")
    assert ct.apply_action("add_phone", {"contactId": cid, "phone": "915550000"})["result"]["changed"] is False
    assert len(ct.load_db()["contacts"][0]["phones"]) == 1, "digits, not spelling, decide identity"


def test_a_company_keeps_every_line_it_has_with_what_each_one_is(ct):
    cid = _add(ct, name="Telefónica", kind="empresa", phone="900 111 222")
    ct.apply_action("add_phone", {"contactId": cid, "phone": "91 555 00 00", "label": "centralita"})
    ct.apply_action("add_email", {"contactId": cid, "email": "facturas@tf.es", "label": "facturación"})
    c = ct.load_db()["contacts"][0]
    assert [r["value"] for r in c["phones"]] == ["900 111 222", "91 555 00 00"]
    assert c["phones"][1]["label"] == "centralita"
    assert c["emails"][0]["label"] == "facturación"
    assert c["phone"] == "900 111 222", "the primary did not move"


def test_removing_a_number_is_the_same_gesture_with_remove(ct):
    cid = _add(ct, name="Acme", phones="900111222, 915550000")
    ct.apply_action("add_phone", {"contactId": cid, "phone": "915550000", "remove": True})
    assert [r["value"] for r in ct.load_db()["contacts"][0]["phones"]] == ["900111222"]


def test_clearing_the_field_empties_the_LIST_too(ct):
    """`normalize` puts the head back from the list, so emptying only the scalar would resurrect it on the
    very next read — which is the kind of write that looks like it worked and is undone in silence."""
    cid = _add(ct, name="Acme", phone="900111222")
    ct.apply_action("update_contact", {"contactId": cid, "clear": "phone"})
    c = ct.load_db()["contacts"][0]
    assert c["phone"] == "" and c["phones"] == []


def test_a_broken_row_costs_ITS_OWN_normalisation_and_nothing_else():
    """`store.load` degrades a migration that RAISES to the seed — an EMPTY directory, which the next save
    would persist. This runs over his real 2 688 rows, so one bad value may never cost the rest."""
    db = {"contacts": [{"phone": "600111222"}, {"phones": object()}, {"email": "x@y.z"}]}
    out = d._migrate(db, 1)
    assert len(out["contacts"]) == 3
    assert out["contacts"][0]["phones"] == [{"value": "600111222", "label": ""}]
    assert out["contacts"][2]["emails"] == [{"value": "x@y.z", "label": ""}]


# ── who answers to a number ─────────────────────────────────────────────────────────────────────────────

def test_a_number_that_is_not_the_primary_still_resolves_to_its_owner(ct):
    """«¿Quién es el 915550000?» — the resolver read only `phone`, so a company's switchboard was a number
    we held and could not recognise."""
    from widgets import directory
    cid = _add(ct, name="Telefónica", kind="empresa", phone="900 111 222")
    ct.apply_action("add_phone", {"contactId": cid, "phone": "915550000", "label": "centralita"})
    assert [c["name"] for c in directory.resolve("915550000")] == ["Telefónica"]


def test_the_record_ANSWERS_with_every_number_not_just_the_first(ct):
    """`read_query` is the door a question about somebody goes through (V2-704). Answering «tel 900111222»
    over a row with three is indistinguishable, to him, from us not holding the other two."""
    cid = _add(ct, name="Telefónica", kind="empresa", phone="900 111 222")
    ct.apply_action("add_phone", {"contactId": cid, "phone": "915550000", "label": "centralita"})
    answer = ct.read_query("¿qué teléfonos tengo de Telefónica?")
    assert "900 111 222" in answer and "915550000" in answer, answer
    assert "centralita" in answer


def test_the_digest_says_HOW_MANY_there_are_without_spending_the_turn_on_them(ct):
    """It rides every turn while the card is open, so it carries the primary and a count — «+2 más» is what
    stops one number reading as «that is all we hold»."""
    cid = _add(ct, name="Telefónica", kind="empresa", phone="900 111 222")
    ct.apply_action("add_phone", {"contactId": cid, "phone": "915550000"})
    ct.apply_action("add_phone", {"contactId": cid, "phone": "910000000"})
    dig = ct.prompt_digest()
    assert "tel 900 111 222 (+2 más)" in dig, dig
    assert "915550000" not in dig, "the other numbers stay out of every turn's prompt"


# ── the platform filter: one predicate, asked by the card AND by the voice ───────────────────────────────

def test_belonging_to_a_platform_is_where_it_CAME_FROM_or_where_you_can_REACH_him():
    """His definition. A contact typed here and later matched to a Telegram account is as much a Telegram
    contact as an imported one, and a tab showing only the imported half would hide the people he talks
    to most."""
    from_google = {"source": "google", "googleId": "people/1"}
    typed_here = {"channels": [{"platform": "telegram", "handle": "@juanito"}]}
    imported = {"externalIds": {"whatsapp": "34600111222@s.whatsapp.net"}}
    assert model.source_matches(from_google, "google-contacts"), "the icon's id and the stored source"
    assert model.source_matches(typed_here, "telegram")
    assert model.source_matches(imported, "whatsapp")
    assert not model.source_matches(typed_here, "whatsapp"), "a Telegram account is not a WhatsApp one"


def test_show_view_answers_the_platform_question_the_icon_asks(ct):
    _add(ct, name="Telefónica", kind="empresa", phone="900111222")
    juan = _add(ct, name="Juan")
    ct.apply_action("set_channel", {"contactId": juan, "platform": "telegram", "handle": "@juanito"})
    r = ct.apply_action("show_view", {"source": "telegram"})["result"]
    assert [m["name"] for m in r["matches"]] == ["Juan"], r


def test_the_hidden_shelf_has_a_spoken_door_too(ct):
    cid = _add(ct, name="Fantasma")
    ct.apply_action("hide_contact", {"contactId": cid})
    assert ct.apply_action("show_view", {})["result"]["count"] == 0
    r = ct.apply_action("show_view", {"hidden": True})["result"]
    assert [m["name"] for m in r["matches"]] == ["Fantasma"], r


def test_the_plug_button_has_an_action_behind_it(ct):
    """A button with no name is a button the voice cannot press — «ábreme los conectores de contactos»."""
    r = ct.apply_action("show_connectors", {})
    assert r["ok"] and r["result"]["screen"] == "connectors"
    assert r["view"]["sel"] == {"screen": "connectors"}, r["view"]
    assert r["result"]["sources"], "it answers with the state of every source, so nothing is invented"


# ── the sync carries them, both ways ────────────────────────────────────────────────────────────────────

def test_google_hands_over_EVERY_number_and_we_hand_them_all_back():
    from connectors.contacts import google_people as g
    person = {"names": [{"displayName": "Acme"}],
              "phoneNumbers": [{"value": "915550000", "formattedType": "Trabajo"},
                               {"value": "600111222", "metadata": {"primary": True},
                                "formattedType": "Móvil"}],
              "emailAddresses": [{"value": "a@acme.es"}]}
    c = g.person_to_contact(person)
    assert [r["value"] for r in c["phones"]] == ["600111222", "915550000"], "primary first"
    assert c["phones"][0]["label"] == "Móvil"
    body = g.contact_to_person(c)
    assert [r["value"] for r in body["phoneNumbers"]] == ["600111222", "915550000"]


def test_a_row_written_before_the_lists_existed_still_pushes_its_one_number():
    from connectors.contacts import google_people as g
    body = g.contact_to_person({"name": "Legacy", "phone": "666777888"})
    assert body["phoneNumbers"] == [{"value": "666777888"}]


def test_googles_other_numbers_are_ADDED_and_never_replace_ours(ct):
    """The same rule `takes_over` protects one field over: a number he typed here is his, so Google
    removing one never removes ours — the card's ✕ is the door for that."""
    from widgets.contactos import gcontacts
    db = ct.load_db()
    gcontacts.merge_imported(db, [{"name": "Acme", "phone": "600111222",
                                   "phones": [{"value": "600111222", "label": "Móvil"}],
                                   "googleId": "people/1"}])
    row = db["contacts"][0]
    model.add_detail(row, "phones", "910000000", "el que puse yo")
    gcontacts.merge_imported(db, [{"name": "Acme", "phones": [{"value": "600111222", "label": "Móvil"}],
                                   "googleId": "people/1"}])
    assert [r["value"] for r in row["phones"]] == ["600111222", "910000000"], row["phones"]
