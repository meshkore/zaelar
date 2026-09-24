"""V2-761 — «ábreme la lista de widgets / el catálogo de apps / qué widgets tengo» opens the wall's Apps tab.

The operator: *«el usuario solo va a poder abrir esto por voz… ábreme la lista de widgets, ábreme la lista de
apps, ábreme el catálogo de apps, ábreme el catálogo de widgets, dime qué widgets tengo disponibles»* — and it
must answer to «apps» and «widgets» alike.

There are three doors a voice order can come through, and each is pinned here:

1. the ACTION MAP (whole-utterance phrases, no model) — the seed packs carry the phrases and validate;
2. the model's `show_panel` tool — its description names the tab and the canon maps the argument onto it;
3. the model's `show_widget` tool (it picks the wrong one: «apps» sounds like a thing to show) — the name
   resolver names the SYSTEM surface `apps`, and the provider and its probe mirror both route that surface
   to the panel instead of asking «which widget?».

And the neighbours that must NOT move, because a descriptor that steals a word from its neighbour is a defect
this repo has paid for three times: «abre la aplicación de música» still opens the music card, «vuelve al
catálogo» (the video card's own words) still names nothing, «abre whatsapp» still opens messaging.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo.actionmap import executor
from nucleo.flash import router_catalog
from nucleo.flash.panel_canon import canon_panel
from widgets import runtime

ENGINE = Path(__file__).resolve().parents[3]


# ── door 3: the name resolver ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("phrase", [
    "ábreme las apps", "abre la lista de widgets", "ábreme el catálogo de widgets", "abre el catálogo de apps",
    "dime qué widgets tengo disponibles", "abre mis aplicaciones", "open my widgets", "open the app catalog",
])
def test_the_catalogue_phrases_name_the_apps_surface(phrase):
    res = runtime.identify(phrase)
    assert res["system"] == "apps" and res["match"] is None, f"{phrase!r} resolved to {res}"


@pytest.mark.parametrize("phrase,widget", [
    ("abre la aplicación de música", "musica"), ("abre el widget de música", "musica"),
    ("abre whatsapp", "mensajeria"), ("ábreme el vídeo", "youtube"),
])
def test_a_named_widget_is_never_stolen_by_the_catalogue(phrase, widget):
    res = runtime.identify(phrase)
    assert res["match"] == widget and res["system"] is None, f"{phrase!r} resolved to {res}"


def test_the_video_cards_own_catalogue_is_not_this_one():
    assert runtime.identify("vuelve al catálogo")["system"] is None


def test_the_provider_and_its_probe_route_the_surface_to_the_panel():
    """Source anchors, because the branch lives in the middle of the provider's streaming loop: the named
    surface is forwarded as the TAB, not hard-coded to the chat."""
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert 'elif _sys in ("chat", "apps"):' in prov
    assert 'emit("panel", "open", extra={"tab": _sys, "src": "flash"})' in prov
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert 'f"panel:{_sys}" if _sys in ("chat", "apps")' in probe


# ── door 2: the show_panel tool ────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("arg,tab", [
    ("apps", "apps"), ("widgets", "apps"), ("lista de widgets", "apps"), ("catálogo de apps", "apps"),
    ("aplicaciones", "apps"), ("mis widgets custom", "apps-custom"), ("apps-custom", "apps-custom"),
    ("conectores whatsapp", "conectores"), ("conectores", "conectores"), ("programadas", "programadas"),
])
def test_the_panel_argument_lands_on_the_apps_tab(arg, tab):
    assert canon_panel(arg) == tab


def test_the_tool_description_names_the_tab():
    tool = next(t for t in router_catalog.TOOLS if t["function"]["name"] == "show_panel")
    assert "'apps'" in tool["function"]["description"]
    assert "widgets" in tool["function"]["description"]


# ── door 1: the action map ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("lang,phrase", [("es", "abreme la lista de widgets"), ("es", "abre el catalogo de apps"),
                                         ("es", "que widgets tengo disponibles"), ("en", "open the widget catalog"),
                                         ("en", "what apps do i have")])
def test_the_seed_packs_carry_the_phrases_and_they_execute(lang, phrase):
    pack = json.loads((ENGINE / f"nucleo/actionmap/seeds/{lang}.json").read_text(encoding="utf-8"))
    hit = next((e for e in pack["entries"] if e.get("phrase") == phrase), None)
    assert hit, f"{lang}: no seed for {phrase!r}"
    assert hit["action"] == {"do": "show_panel", "tab": "apps", "action": "open"}
    assert executor.validate(hit["action"]) == "", "the executor refuses the apps tab"


def test_the_packs_were_versioned_so_existing_installs_import_them():
    """A pack only re-imports on a version bump (`store.seed`) — new phrases in an old version reach nobody."""
    for lang in ("es", "en"):
        pack = json.loads((ENGINE / f"nucleo/actionmap/seeds/{lang}.json").read_text(encoding="utf-8"))
        assert pack["version"] >= 10, f"{lang}: the pack carries the apps phrases under an old version"
