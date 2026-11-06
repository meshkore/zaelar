"""V2-806 F5 — his rules are listed and edited BY ID: over HTTP for ⚙ Settings → Rules, and the panel is built from
the panel's own pieces.

The class: before the table there was nothing to list — six stores, no ids — so «what rules do I have?» had no
answer and a rule could only be removed by guessing which sentence looked most like his words. Now every row has an
id; the list is the table grouped by scope with its source, an edit is checked against its key's declared domain,
a default is overridden (never deleted) and his rows can be switched off or deleted. Voice listing and removal by id
are measured in `test_a_rule_is_understood_once_when_written.py`.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rules
from rules.api import router

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def client():
    rules._reset_for_tests()
    app = FastAPI()
    app.include_router(router)
    yield TestClient(app)
    rules._reset_for_tests()


def _rows(client) -> dict:
    return {r["id"]: r for g in client.get("/api/rules").json()["groups"] for r in g["rows"]}


def test_the_list_is_the_table_grouped_by_scope_with_its_source(client):
    mine = rules.add("messaging/email/send_new", "gate", "consent", "ask", text="pregúntame antes de mandar correos")
    body = client.get("/api/rules").json()
    assert body["ok"] and body["groups"][0]["scope"] == "global", "the broadest scope first"
    by_scope = {g["scope"]: g["rows"] for g in body["groups"]}
    assert [(r["id"], r["source"]) for r in by_scope["messaging/email/send_new"]] == [(mine["id"], "user")]
    assert any(r["source"] == "default" for r in by_scope["messaging/*/autorespond"])
    assert _rows(client)[mine["id"]]["choices"] == ["allow", "ask", "never"], "the closed set the panel offers"


def test_an_edit_is_checked_against_its_keys_domain(client):
    mine = rules.add("messaging/email/send_new", "gate", "consent", "ask")
    assert client.patch(f"/api/rules/{mine['id']}", json={"value": "maybe"}).status_code == 400
    assert client.patch(f"/api/rules/{mine['id']}", json={"value": "allow"}).json()["rule"]["value"] == "allow"
    assert rules.gate(rules.path(cls="messaging.send_new@email")) == "allow"
    knob = "default:confirm_short_actions@voice"
    assert client.patch(f"/api/rules/{knob}", json={"value": "no"}).status_code == 400, "a yes/no knob takes a bool"


def test_a_default_is_overridden_never_deleted_nor_switched_off(client):
    dflt = "default:consent@messaging/*/autorespond"
    assert client.delete(f"/api/rules/{dflt}").status_code == 400
    assert client.patch(f"/api/rules/{dflt}", json={"active": False}).status_code == 400
    edited = client.patch(f"/api/rules/{dflt}", json={"value": "ask"}).json()["rule"]
    assert edited["source"] == "user" and edited["id"] != dflt
    assert _rows(client)[dflt]["value"] == "never", "the factory row stays as shipped"


def test_his_row_is_switched_off_and_deleted_by_id(client):
    mine = rules.add("messaging/email/send_new", "gate", "consent", "never")
    client.patch(f"/api/rules/{mine['id']}", json={"active": False})
    assert _rows(client)[mine["id"]]["live"] is False and rules.gate(rules.path(cls="messaging.send_new@email")) == "allow"
    assert client.delete(f"/api/rules/{mine['id']}").json()["ok"]
    assert mine["id"] not in _rows(client)
    assert client.delete(f"/api/rules/{mine['id']}").status_code == 404


def test_the_settings_section_is_built_from_the_panels_own_pieces():
    panel = (ENGINE / "frontend/app/components/ConfigPanel.js").read_text("utf-8")
    sec = (ENGINE / "frontend/app/components/RulesSection.js").read_text("utf-8")
    assert '{ id: "rules", icon: LIST_ICON }' in panel and "mountRules(" in panel, "a sub-item of Settings, mounted on screen"
    for piece in ('class="cf-row2"', 'class="cf-sub"', "cf-btn cf-btn-ghost", 'class="cf-panel-sec"'):
        assert piece in sec, piece
    assert "r.choices" in sec, "the closed set comes from the server, never a second list in the page"
    assert "/api/rules" in (ENGINE / "frontend/app/services/api.js").read_text("utf-8")
    assert "rules_router" in (ENGINE / "server/__init__.py").read_text("utf-8")


# ── he never sees a scope, a key or an id ───────────────────────────────────────────────────────────────

_TECHNICAL = ("/", "@", "widget:", "item:", "default:", "r_", "m_")


def _his_rows():
    return [
        rules.add("messaging/email/send_new", "gate", "consent", "ask", text="pregúntame antes de mandar correos"),
        rules.add("messaging/*/send_new", "gate", "consent", "allow", except_=["messaging/telegram", "item:c7"]),
        rules.add("widget:youtube", "pref", "note", "nada de vídeos largos", text="nada de vídeos largos"),
        rules.add("widget:agenda/add_meeting", "pref", "note", "reuniones de 30 minutos", text="reuniones de 30 minutos"),
        rules.add("item:c7", "gate", "consent", "never"),
        rules.add("voice", "pref", "fillers", "off"),
    ]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_nothing_the_panel_shows_is_a_scope_a_key_or_an_id(client, lang):
    from tests.lang import speaking
    with speaking(lang):
        mine = _his_rows()
        body = client.get("/api/rules").json()
    ids = {r["id"] for g in body["groups"] for r in g["rows"]}
    shown = [g["label"] for g in body["groups"]]
    for g in body["groups"]:
        for r in g["rows"]:
            shown += [r["name"], *r["except_labels"]]
    for s in shown:
        assert s.strip(), "every place and every row has words"
        assert not any(tok in s for tok in _TECHNICAL), f"technical text on his screen: {s!r}"
        assert not any(i in s for i in ids), f"an id on his screen: {s!r}"
    labels = {g["scope"]: g["label"] for g in body["groups"]}
    assert labels["messaging/email/send_new"] == ("Correo · enviar mensajes nuevos" if lang == "es"
                                                  else "Email · send new messages")
    assert labels["global"] == ("En general" if lang == "es" else "In general")
    assert labels["widget:youtube"] == "YouTube"
    assert {r["name"] for r in _rows(client).values() if r["id"] == mine[0]["id"]} == \
        {"pregúntame antes de mandar correos"}, "the row label stays his own words"
