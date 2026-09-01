"""V2-541 — the contacts widget: ONE directory for every identity, and its view is an ACTION.

Born from the operator's direct order (2026-09-01): one NATIVE widget for the whole contacts archive —
people, restaurants, plumbers, cafés, companies — never a per-kind widget (a generated
`restaurantes-favoritos-operador` was deleted the same day so only this one exists). This settles the
question the V2-523 plan left open: a favourite place IS a directory entry, with `favorite` as a flag.

The view lessons are applied at birth instead of after an incident: filtering what is on screen has a NAME
in the manifest (the agenda's V2-540 `show_day` measurement — an undeclared capability is one the model
narrates), the push rides a witness counter with server-side freshness, and `apply_action` survives the
payload the canvas actually sends (`{**payload, "q": ...}` — node 4.95's lesson).
"""
from __future__ import annotations

import json
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def ct(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real directory."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    return d


def _as_the_canvas_sends_it(payload):
    """`desktop.js` builds EVERY action payload as `{...payload, q}` — never anything else (V2-540)."""
    return {**payload, "q": ""}


def _manifest():
    return json.loads((ENGINE / "widgets" / "contactos" / "manifest.json").read_text(encoding="utf-8"))


# ── The manifest IS the vocabulary ───────────────────────────────────────────────────────────────────────────

def test_every_capability_EXISTS_in_the_manifest_or_the_model_cannot_choose_it(ct):
    m = _manifest()
    assert set(m["actions"]) == {"add_contact", "update_contact", "remove_contact", "set_favorite",
                                 "link_contact", "show_view", "show_contact"}


def test_the_view_action_speaks_the_everyday_phrasing_not_a_schema(ct):
    desc = _manifest()["actions"]["show_view"]["desc"].lower()
    assert "favorito" in desc, "the model needs «mi restaurante favorito», not a filter schema"
    assert "no filtra" in desc, "it must say that showing the widget again cannot do this"


def test_removing_a_contact_asks_first(ct):
    a = _manifest()["actions"]["remove_contact"]
    assert a.get("confirm") is True, "deleting a real contact is irreversible and must confirm"


def test_the_directory_survives_a_reset_by_declaration(ct):
    m = _manifest()
    assert m.get("data", {}).get("durable") is True, "the operator's contacts are not a derived surface"


# ── The write does not invent, and never duplicates ──────────────────────────────────────────────────────────

def test_a_nameless_add_is_an_error_that_teaches_the_retry_shape(ct):
    res = ct.apply_action("add_contact", _as_the_canvas_sends_it({"city": "Soria"}))
    assert res["ok"] is False and "name" in res["error"], res
    assert ct.view_data()["count"] == 0, "an error must not leave a half row behind"


def test_same_name_and_city_UPDATES_instead_of_duplicating(ct):
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Elfo On", "kind": "place", "group": "restaurantes", "city": "Soria"}))
    res = ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "elfo ón", "city": "soria", "favorite": "sí", "phone": "600111222"}))
    assert res["ok"] and res["result"]["updated"] is True, res.get("result")
    d = ct.view_data()
    assert d["count"] == 1
    c = d["contacts"][0]
    assert c["favorite"] is True and c["phone"] == "600111222"
    assert c["groups"] == ["restaurantes"], "the update must keep the labels it already had"


def test_a_different_city_is_a_DIFFERENT_contact(ct):
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Casa Pepe", "city": "Soria"}))
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Casa Pepe", "city": "Valls"}))
    assert ct.view_data()["count"] == 2, "two branches of one franchise are two entries"


def test_groups_arrive_as_a_comma_string_or_a_list_and_dedup(ct):
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Marta", "group": "amigos, amigos del trabajo, Amigos"}))
    c = ct.view_data()["contacts"][0]
    assert c["groups"] == ["amigos", "amigos del trabajo"], c["groups"]


# ── update / remove / favorite / link ────────────────────────────────────────────────────────────────────────

def _seed_three(ct):
    ct.apply_action("add_contact", {"name": "Elfo On", "kind": "place", "group": "restaurantes",
                                    "city": "Soria", "favorite": True})
    ct.apply_action("add_contact", {"name": "Bar Sol", "kind": "place", "group": "restaurantes",
                                    "city": "Barcelona", "favorite": True})
    ct.apply_action("add_contact", {"name": "Juan", "kind": "person", "group": "fontaneros", "city": "Soria"})
    return {c["name"]: c["id"] for c in ct.view_data()["contacts"]}


def test_update_without_an_id_is_an_error_and_group_ADDS_while_groups_REPLACES(ct):
    ids = _seed_three(ct)
    assert ct.apply_action("update_contact", _as_the_canvas_sends_it({"name": "X"}))["ok"] is False
    ct.apply_action("update_contact", {"contactId": ids["Juan"], "group": "amigos"})
    juan = next(c for c in ct.view_data()["contacts"] if c["id"] == ids["Juan"])
    assert juan["groups"] == ["fontaneros", "amigos"]
    ct.apply_action("update_contact", {"contactId": ids["Juan"], "groups": "vecinos"})
    juan = next(c for c in ct.view_data()["contacts"] if c["id"] == ids["Juan"])
    assert juan["groups"] == ["vecinos"]


def test_removing_a_parent_never_leaves_a_dangling_link(ct):
    ids = _seed_three(ct)
    ct.apply_action("link_contact", {"contactId": ids["Juan"], "parentId": ids["Elfo On"]})
    ct.apply_action("remove_contact", {"contactId": ids["Elfo On"]})
    juan = next(c for c in ct.view_data()["contacts"] if c["id"] == ids["Juan"])
    assert juan["parentId"] == "", "a pointer to a removed contact paints a dead breadcrumb"


def test_a_link_to_yourself_or_a_cycle_is_refused(ct):
    ids = _seed_three(ct)
    assert ct.apply_action("link_contact",
                           {"contactId": ids["Juan"], "parentId": ids["Juan"]})["ok"] is False
    ct.apply_action("link_contact", {"contactId": ids["Juan"], "parentId": ids["Elfo On"]})
    res = ct.apply_action("link_contact", {"contactId": ids["Elfo On"], "parentId": ids["Juan"]})
    assert res["ok"] is False, "linking both ways would make the breadcrumb walk forever"


def test_set_favorite_defaults_to_TRUE_and_parses_spoken_booleans(ct):
    ids = _seed_three(ct)
    ct.apply_action("set_favorite", {"contactId": ids["Juan"]})
    juan = next(c for c in ct.view_data()["contacts"] if c["id"] == ids["Juan"])
    assert juan["favorite"] is True
    ct.apply_action("set_favorite", {"contactId": ids["Juan"], "favorite": "no"})
    juan = next(c for c in ct.view_data()["contacts"] if c["id"] == ids["Juan"])
    assert juan["favorite"] is False


# ── The view is an action that ANSWERS ───────────────────────────────────────────────────────────────────────

def test_the_favourite_restaurant_in_barcelona_is_ONE_call(ct):
    """The operator's own example: «¿cuál es mi restaurante favorito en Barcelona?». The same call filters
    the screen AND returns the answer, so replying is never a promise."""
    _seed_three(ct)
    res = ct.apply_action("show_view", _as_the_canvas_sends_it(
        {"group": "restaurante", "city": "Barcelona", "favorites": "true"}))
    assert res["ok"] and res["result"]["count"] == 1, res.get("result")
    assert res["result"]["matches"][0]["name"] == "Bar Sol"


def test_the_plumbers_we_have_in_soria(ct):
    _seed_three(ct)
    res = ct.apply_action("show_view", {"group": "fontaneros", "city": "Soria"})
    assert [m["name"] for m in res["result"]["matches"]] == ["Juan"]


def test_the_token_MOVES_every_time_even_for_the_same_filter(ct):
    """The agenda's V2-540 counter, applied at birth: the canvas re-renders only when the JSON signature
    changes and the widget re-applies only when the token moves — with the filter as the token, asking twice
    would move nothing."""
    _seed_three(ct)
    a = ct.apply_action("show_view", {"group": "restaurantes"})["view"]
    b = ct.apply_action("show_view", {"group": "restaurantes"})["view"]
    assert a["sel"] == b["sel"] and b["n"] > a["n"], (a, b)


def test_a_stale_push_is_NOT_served_to_a_widget_that_opens_days_later(ct, monkeypatch):
    _seed_three(ct)
    ct.apply_action("show_view", {"group": "restaurantes"})
    assert ct.view_data()["view"] is not None
    monkeypatch.setattr(ct, "_VIEW_TTL_S", -1)
    assert ct.view_data()["view"] is None, "a week-old filter is still being pushed at a fresh mount"


def test_showing_a_view_CHANGES_NOTHING_the_operator_owns(ct):
    _seed_three(ct)
    before = ct.view_data()["contacts"]
    ct.apply_action("show_view", {"group": "restaurantes", "favorites": True})
    assert ct.view_data()["contacts"] == before


def test_show_contact_pushes_the_detail_and_returns_the_linked_people(ct):
    ids = _seed_three(ct)
    ct.apply_action("link_contact", {"contactId": ids["Juan"], "parentId": ids["Elfo On"]})
    res = ct.apply_action("show_contact", {"contactId": ids["Elfo On"]})
    assert res["view"]["sel"] == {"contactId": ids["Elfo On"]}
    assert [k["name"] for k in res["result"]["linked"]] == ["Juan"]


# ── The brain can point at things ────────────────────────────────────────────────────────────────────────────

def test_ref_index_exposes_every_contact_by_name_with_the_action_field(ct):
    ids = _seed_three(ct)
    idx = ct.ref_index()
    assert {r["id"] for r in idx} == set(ids.values())
    assert all(r["field"] == "contactId" for r in idx)
    labels = {r["id"]: r["label"] for r in idx}
    assert labels[ids["Elfo On"]] == "Elfo On (Soria)", "the city disambiguates two same-named entries"
