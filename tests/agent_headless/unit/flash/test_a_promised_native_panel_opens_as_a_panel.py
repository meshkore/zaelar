"""A promised NATIVE panel opens as a panel, never as the card a word in the sentence names (node 2.405).

V2-834 T14, use case `connect-email-by-voice` (sandbox, 2026-11-02): «Ábreme el panel de conectores con el correo…» —
the model promised «abro el panel de conectores con el correo ya puesto» and called nothing; the promise backstop,
which knew only canvas cards, resolved the sentence by its «correo» to the MESSAGING card and opened that. The
connectors tab of the wall was not a declared surface, so the name resolver could not name it.

Mechanism pinned here: `conectores` is a declared system surface (aliases ES/EN, mirrored in the JS registry), the
resolver names it over a card word in the same sentence, and the backstop opens it as a panel with the connector
the words name.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from nucleo.acts import wall_tab
from nucleo.flash import router
from widgets import runtime


def open_named_panel(said, emit, *, proposed, card, acted=None, fired=None):
    return wall_tab.open_named_panel(said, emit, proposed=proposed, card=card, acted={} if acted is None else acted,
                                     _router=router, _tool_fired=set() if fired is None else fired)

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("said, connector", [
    ("Pero Gmail se conecta con una contraseña de aplicación de Google, ¿no? Ábreme el panel de conectores con el "
     "correo y dime que el formulario me la pedirá ahí.", "email"),
    ("Open the connectors panel with my email, the form will ask me for the app password.", "email"),
    ("abre los conectores", ""),
])
def test_the_words_name_the_connectors_panel(said, connector):
    assert (runtime.identify(said) or {}).get("system") == "conectores"
    got, acted, fired = [], {}, set()
    assert open_named_panel(said, lambda *a, **k: got.append((a, k)), proposed=True, card="", acted=acted, fired=fired)
    assert acted == {"widget": True} and fired == {"show_panel"}, "through THE show_panel door (S1 audit H6)"
    assert got[0][0] == ("panel", "open") and got[0][1]["extra"].get("connector", "") == connector, got
    assert not open_named_panel(said, lambda *a, **k: None, proposed=False, card=""), "nothing promised: nothing opens"


@pytest.mark.parametrize("said", ["enséñame el correo", "show me my email", "abre la agenda"])
def test_a_card_is_still_a_card(said):
    assert not open_named_panel(said, lambda *a, **k: None, proposed=True, card="")


def test_the_promise_backstop_opens_it():
    src = (ROOT / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    assert "open_named_panel(_op_text, emit, proposed=" in src and "acted=acted" in src and "_tool_fired=_tool_fired" in src
    ast.parse(src)


def test_a_panel_the_model_already_opened_is_not_opened_twice():
    """The one door keeps its own once-per-turn mark: the backstop after a real `show_panel` emits nothing more."""
    got = []
    said = "Open the connectors panel with my email."
    assert not open_named_panel(said, lambda *a, **k: got.append(a), proposed=True, card="", fired={"show_panel"})
    assert got == []
