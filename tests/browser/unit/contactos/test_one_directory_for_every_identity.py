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
                                 "link_contact", "show_view", "show_contact",
                                 # V2-683 — by WHICH channel this person is written to, and which is his.
                                 "set_channel",
                                 # V2-699 — the Google Contacts link. Declared rather than left as HTTP
                                 # endpoints, because an endpoint is a door the VOICE cannot open.
                                 # `import_google` is the retired name of `sync_contacts`, kept as an alias
                                 # so a model that learned it does not start getting «acción desconocida».
                                 "sync_contacts", "import_google", "connect", "disconnect"}


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


# ── The brain can SEE the directory, not just point at it (V2-576) ───────────────────────────────────────────
#
# Session 0a93de06 (2026-09-04): asked «¿cuántos restaurantes favoritos tenemos?», the brain answered from
# stale memory pills («one») while the open card showed four — then, confronted with the mismatch, invented
# «la vista actual no lo muestra». `ref_index` gives labels without meaning: nothing in the prompt said
# «these ARE all the favourites, four in total». The digest is the widget stating its own truth.

def test_prompt_digest_states_the_authoritative_counts_and_every_row(ct):
    _seed_three(ct)
    d = ct.prompt_digest()
    assert "3 entradas" in d and "2 favoritas" in d
    for name in ("Elfo On", "Bar Sol", "Juan"):
        assert name in d
    # The claim that beats the stale pill: the block declares itself the source of truth.
    assert "MANDA" in d and "memoria" in d


def test_prompt_digest_of_an_empty_directory_says_empty_not_nothing(ct):
    d = ct.prompt_digest()
    assert "VACÍO" in d and "0 contactos" in d


def test_prompt_digest_names_the_filter_the_operator_is_looking_through(ct):
    _seed_three(ct)
    ct.apply_action("show_view", {"favorites": True, "city": "Soria"})
    d = ct.prompt_digest()
    assert "solo favoritos" in d and "city: Soria" in d


def test_prompt_digest_caps_rows_but_never_lies_about_the_total(ct):
    for i in range(18):
        ct.apply_action("add_contact", {"name": f"Persona {i:02d}", "kind": "person"})
    d = ct.prompt_digest()
    assert "18 entradas" in d
    assert "y 3 entradas más" in d


def test_the_open_card_digest_reaches_the_flash_prompt(ct):
    """End to end through `brief.for_prompt`: with the card OPEN the digest travels (labelled as on-screen
    content and taking precedence over the bare items line); with it CLOSED the prompt pays nothing."""
    _seed_three(ct)
    from widgets import brief
    abierto = brief.for_prompt(open_ids={"contactos"}, query="mis restaurantes favoritos")
    assert "contenido en pantalla" in abierto and "3 entradas" in abierto and "2 favoritas" in abierto
    cerrado = brief.for_prompt(open_ids=set(), query="mis restaurantes favoritos")
    assert "2 favoritas" not in cerrado


# ── V2-693 · ONE TELEGRAM ACCOUNT BELONGS TO ONE CONTACT ─────────────────────────────────────────────────
def test_a_second_NAME_for_an_account_we_already_hold_is_the_SAME_contact(ct):
    """⚠️ The operator found this himself, live: «¿cómo vamos a tener dos contactos que tienen el mismo
    nickname de Telegram?». `add_contact` deduped on name+city ALONE, so the same person under a second
    name made a second row — and then `send_to` had two candidates for one human being.

    An account is a stronger identity than a name: a name can be said two ways, a Telegram username belongs
    to exactly one account."""
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Pruebas Zaelar", "channels": {"platform": "telegram", "handle": "@cryptonite_fund"}}))
    res = ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Cryptonite", "channels": {"platform": "telegram", "handle": "cryptonite_fund"}}))
    assert res["ok"] and res["result"]["updated"] is True, res.get("result")
    assert ct.view_data()["count"] == 1, "one Telegram account cannot be two contacts"


def test_the_account_matches_through_the_id_the_traffic_taught_us(ct):
    """The two halves of a Telegram identity are the handle the operator typed and the numeric id the
    platform resolved. Either one is proof, in either direction."""
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Cryptonite", "channels": {"platform": "telegram", "handle": "@cryptonite_fund",
                                            "chatId": "7477656357"}}))
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "El de las cripto", "channels": {"platform": "telegram", "handle": "7477656357"}}))
    assert ct.view_data()["count"] == 1


def test_a_DIFFERENT_account_is_still_a_different_contact(ct):
    """The guard must not collapse two people who simply both have Telegram."""
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Ana", "channels": {"platform": "telegram", "handle": "@ana"}}))
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Berta", "channels": {"platform": "telegram", "handle": "@berta"}}))
    assert ct.view_data()["count"] == 2


def test_an_AMBIGUOUS_account_writes_nothing_rather_than_guessing(ct, monkeypatch):
    """Two contacts already holding one account is a finding, not a merge — the `note_inbound` rule
    (V2-541), applied at the other door. It creates a new row instead of picking one of them."""
    from widgets.contactos import data as d
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Uno", "channels": {"platform": "telegram", "handle": "@dup"}}))
    db = d.load_db()
    twin = dict(db["contacts"][0])
    twin["id"] = "cX"
    twin["name"] = "Dos"
    db["contacts"].append(twin)
    d.store.save(d.WIDGET_ID, db)
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Tres", "channels": {"platform": "telegram", "handle": "@dup"}}))
    assert ct.view_data()["count"] == 3, "an ambiguity must not be silently resolved onto one of them"


def test_the_id_the_connector_RESOLVED_is_written_back_to_the_contact(ct):
    """⚠️ V2-693 — this mapping existed nowhere else and was thrown away, and that is what grew the twin.

    The operator asks by name, the resolver hands the connector a HANDLE, the connector asks Telegram who
    that is and gets a numeric chat id back. Without this, the same person's reply arrived as a stranger.
    """
    from widgets import directory
    ct.apply_action("add_contact", _as_the_canvas_sends_it(
        {"name": "Cryptonite", "channels": {"platform": "telegram", "handle": "@cryptonite_fund"}}))
    cid = ct.view_data()["contacts"][0]["id"]
    assert directory.note_reached("telegram", "7477656357", cid) is True
    ch = ct.view_data()["contacts"][0]["channels"][0]
    assert ch["chatId"] == "7477656357"
    assert ch["handle"] == "@cryptonite_fund", "the operator's own handle is never overwritten by an id"
    assert directory.note_reached("telegram", "7477656357", cid) is False, "nothing new: no write"


def test_learning_an_id_for_a_contact_that_is_GONE_writes_nothing(ct):
    from widgets import directory
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Nadie"}))
    assert directory.note_reached("telegram", "999", "no-existe") is False
    assert directory.note_reached("telegram", "", ct.view_data()["contacts"][0]["id"]) is False


# ── The name as the operator SPELLS it (V2-698) ─────────────────────────────────────────────────────────────

def test_a_name_one_letter_off_resolves_when_it_is_the_only_near_match(ct):
    """Measured 2026-09-15: he dictates «Kryptonite», the row says «Cryptonite», and `send_to` refused with
    «no tengo a Kryptonite en el directorio» — the worker had to guess the spelling to get his order out."""
    from widgets import directory
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Cryptonite", "telegram": "@cryptonite_fund"}))
    assert [c["name"] for c in directory.resolve("Kryptonite")] == ["Cryptonite"]


def test_two_near_names_stay_a_refusal_never_a_guess(ct):
    """Writing to the wrong person is the failure the fuzzy match must never trade for."""
    from widgets import directory
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Marta", "phone": "+34600000001"}))
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Marto", "phone": "+34600000002"}))
    assert directory.resolve("Marte") == []


def test_a_name_that_is_simply_not_there_still_resolves_to_nobody(ct):
    from widgets import directory
    ct.apply_action("add_contact", _as_the_canvas_sends_it({"name": "Cryptonite", "telegram": "@cryptonite_fund"}))
    assert directory.resolve("Federico") == []
