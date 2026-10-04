"""Asking to connect a channel must LAND somewhere (V2-520, re-anchored 2026-10-04).

Reported live by the operator 2026-08-31: "conéctame el correo" opened the messaging card and nothing
else — no dialog, no question about which mail provider. V2-520 answered with a declared widget intent
(`open_connectors` + a `connect_focus` the card honoured once). On 2026-10-04 the widgets' own connect
screens were removed: there is ONE door to connect a service, the ⚙ «Conectores» section opened on that
connector with its step-by-step guide (`show_panel(panel='conectores', connector=…)`, canon in
`nucleo/flash/connector_canon.py`; by hand, `ctx.openConnector` from the card's plug or a channel icon).

What this file pins is the same intent on the new door: the phrase names a connector the section knows,
the manifest tells the brain WHERE connecting lives instead of declaring a connect action of its own, and
the voice still transports an intention, never a credential.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo.flash.connector_canon import canon_connector

MANIFEST = Path(__file__).resolve().parents[4] / "widgets" / "mensajeria" / "manifest.json"
WIDGET_JS = MANIFEST.with_name("widget.js")


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_card_declares_no_connect_action_and_says_where_connecting_lives():
    """A connect action on the card would give «conéctame el correo» two plausible destinations again."""
    man = _manifest()
    acts = man.get("actions") or {}
    assert not {"connect", "disconnect", "open_connectors"} & set(acts)
    assert "show_panel(panel='conectores'" in man["whenToUse"], "the routing line has to say where it IS"


@pytest.mark.parametrize("phrase,cx", [("conéctame el correo", "email"), ("connect my email", "email"),
                                       ("conecta whatsapp", "whatsapp"), ("vincula telegram", "telegram")])
def test_asking_to_connect_a_channel_names_its_connector(phrase, cx):
    assert canon_connector(phrase) == cx


def test_an_unknown_platform_still_opens_the_section():
    """«conéctame una cosa» → the section opens on its LIST rather than refusing: the catalogue IS the answer."""
    assert canon_connector("señales de humo") == ""
    assert canon_connector("") == ""


def test_the_intent_never_carries_a_credential():
    """Opening a guide is not connecting. A password or an OAuth round-trip is never done by voice: the door
    takes a connector NAME and nothing else, so a secret spoken into the argument never travels past it."""
    out = canon_connector("email password hunter2")
    assert out == "email" and "hunter2" not in out


def test_the_card_has_no_connect_screen_of_its_own_and_its_plugs_open_the_one_door():
    """The V2-520 wizard (`connect_focus` → `_screen = wizard`) is gone from the card; what is left is the door."""
    src = WIDGET_JS.read_text(encoding="utf-8")
    assert "_focusDone" not in src and 'view:"wizard"' not in src
    assert "ctx.openConnector(" in src, "the channel icons and the plug reach the ⚙ Conectores section"
