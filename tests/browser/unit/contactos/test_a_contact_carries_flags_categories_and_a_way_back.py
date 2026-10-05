"""A contact carries FLAGS and a CATEGORY, and a deletion has a way back (operator review of the directory, 2026-10-05).

«Revisa que el widget de contactos sea completo: buscar, modificar, añadir, borrar, filtrar, añadir clasificación (si
es contacto personal, restaurante), flags como favorito, cerrado…». Measured before this: the only flags were
`favorite` and `hidden`, so «that restaurant closed» had nowhere to go; `kind: "restaurante"` silently became a
PERSON; a deletion was final while the agenda's had a trash; and a filter pushed as «empresa» filtered the spoken
answer and left the card showing everything. One flag vocabulary (`favorite` stays its own field — four modules read
it), the category is a label said in a field of its own, and `remove_contact` keeps the row for `restore_contact`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_DIR = Path(__file__).resolve().parents[4] / "widgets" / "contactos"


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    return d


def _row(ct, name):
    return next(c for c in ct.load_db()["contacts"] if c["name"] == name)


def test_a_category_is_a_label_and_a_place_word_is_a_place(ct):
    ct.apply_action("add_contact", {"name": "Casa Lucio", "kind": "restaurante", "category": "Restaurantes"})
    ct.apply_action("add_contact", {"name": "Bar Pepe", "kind": "restaurant"})
    ct.apply_action("add_contact", {"name": "Laura", "categories": ["personal", "familia"]})
    assert _row(ct, "Casa Lucio")["kind"] == "place" and _row(ct, "Casa Lucio")["groups"] == ["Restaurantes"]
    assert _row(ct, "Bar Pepe")["kind"] == "place"
    assert _row(ct, "Laura")["groups"] == ["personal", "familia"] and _row(ct, "Laura")["kind"] == "person"
    ct.apply_action("update_contact", {"contactId": _row(ct, "Laura")["id"], "category": "trabajo"})
    assert "trabajo" in _row(ct, "Laura")["groups"]


def test_a_flag_is_set_filtered_and_cleared(ct):
    ct.apply_action("add_contact", {"name": "Casa Lucio", "kind": "place"})
    cid = _row(ct, "Casa Lucio")["id"]
    assert ct.apply_action("set_flag", {"contactId": cid, "flag": "cerrado"}).get("ok")
    assert _row(ct, "Casa Lucio")["flags"] == ["closed"]
    got = ct.apply_action("show_view", {"flag": "closed"})
    assert [m["name"] for m in got["result"]["matches"]] == ["Casa Lucio"]
    assert got["result"]["matches"][0].get("flags") == ["closed"], "the brain reads the flag in the result"
    assert ct.apply_action("set_flag", {"contactId": cid, "flag": "closed", "on": False}).get("ok")
    assert not _row(ct, "Casa Lucio").get("flags")


def test_favorite_is_one_meaning_whichever_door(ct):
    ct.apply_action("add_contact", {"name": "Ana"})
    cid = _row(ct, "Ana")["id"]
    ct.apply_action("set_flag", {"contactId": cid, "flag": "favorito"})
    assert _row(ct, "Ana")["favorite"] is True and "favorite" not in (_row(ct, "Ana").get("flags") or [])


def test_an_unknown_flag_is_refused_with_the_vocabulary(ct):
    ct.apply_action("add_contact", {"name": "Ana"})
    got = ct.apply_action("set_flag", {"contactId": _row(ct, "Ana")["id"], "flag": "purple"})
    assert got.get("ok") is False and "closed" in got.get("error", "")


def test_a_deleted_contact_comes_back_as_it_was(ct):
    ct.apply_action("add_contact", {"name": "Iván", "city": "Soria", "phone": "+34600111222"})
    row = _row(ct, "Iván")
    db = ct.load_db()
    db["contacts"][0]["googleId"] = "people/c42"
    from widgets import store
    store.save("contactos", db)
    ct.apply_action("remove_contact", {"contactId": row["id"]})
    assert not [c for c in ct.load_db()["contacts"] if c["name"] == "Iván"]
    assert "people/c42" in ct.load_db()["sync"]["pendingDeletes"]
    got = ct.apply_action("restore_contact", {})
    assert got.get("ok"), got
    back = _row(ct, "Iván")
    assert (back["id"], back["city"], back["phone"]) == (row["id"], "Soria", "+34600111222")
    assert "people/c42" not in ct.load_db()["sync"]["pendingDeletes"], "the queued Google deletion is withdrawn"
    assert ct.apply_action("restore_contact", {}).get("ok") is False


def test_a_pushed_kind_is_the_one_the_card_filters_by(ct):
    ct.apply_action("add_contact", {"name": "Acme", "kind": "company"})
    ct.apply_action("show_view", {"kind": "empresa"})
    assert ct.load_db()["view"]["sel"]["kind"] == "company", "the card compares kinds literally"


def test_the_members_of_a_group_are_a_view(ct):
    db = ct.load_db()
    db["contacts"] = [{"id": "g1", "kind": "group", "name": "Familia", "members": []}]
    from widgets import store
    store.save("contactos", db)
    ct.apply_action("show_contact_members", {"contactId": "g1"})
    assert ct.load_db()["view"]["sel"] == {"contactId": "g1"}


def test_the_manifest_and_the_card_carry_it():
    acts = json.loads((_DIR / "manifest.json").read_text("utf-8"))["actions"]
    assert {"set_flag", "restore_contact"} <= set(acts)
    assert "flag" in acts["show_view"]["payload"] and "category" in acts["add_contact"]["payload"]
    assert "permanent" not in acts["remove_contact"].get("confirm_q", "").lower()
    js = (_DIR / "widget.js").read_text("utf-8")
    assert "sel.flag" in js and "c.flags" in js, "a flag pushed by voice must filter the card, and show on the row"
    for lang in ("es", "en"):
        bundle = json.loads((_DIR.parents[1] / "i18n" / "bundles" / f"{lang}.json").read_text("utf-8"))
        assert bundle.get("widgets.contactos.flag_closed"), lang
