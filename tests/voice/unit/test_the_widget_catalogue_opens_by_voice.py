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
    # his exact words in session 952923e3 (2026-09-24), each of which ended in «no tengo un catálogo»:
    "Enséñame el catálogo de aplicaciones.", "Vale, enséñame el catálogo de widgets.",
    "Vale, ábreme la lista de widgets customizados.", "¿Qué APPs tengo customizadas?",
    "O los widgets. Ábreme esa lista.",
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


@pytest.mark.parametrize("phrase,tab", [
    ("Vale, ábreme la lista de widgets customizados.", "apps-custom"), ("¿Qué APPs tengo customizadas?", "apps-custom"),
    ("abre mis widgets personalizados", "apps-custom"), ("Enséñame el catálogo de aplicaciones.", "apps"),
])
def test_asking_for_HIS_widgets_opens_the_custom_sub_tab(phrase, tab):
    from nucleo.flash.panel_canon import apps_tab
    assert apps_tab(phrase) == tab


def test_the_models_catalogue_says_which_widgets_are_his():
    """«Las tarjetas personalizadas que tengas tú hechas no me salen en la lista que veo» — the fact existed
    (`origin`, `forked_from`) and never reached the model. The row now carries it."""
    from widgets import brief, runtime as rt, selection
    cat = [{"id": "youtube", "whenToUse": "vídeo", "origin": "user", "forked_from": {"origin": "builtin"}},
           {"id": "canvas-shows-day", "whenToUse": "mi día", "origin": "user"},
           {"id": "musica", "whenToUse": "música"}]
    real = selection.candidates
    selection.candidates = lambda *a, **k: [{"w": w} for w in cat]
    try:
        out = brief.for_prompt([], [], "")
    finally:
        selection.candidates = real
    rows = {ln.split(" — ")[0].strip("- "): ln for ln in out.splitlines() if ln.startswith("- ")}
    assert "custom (su copia de la de sistema)" in rows["youtube"]
    assert "custom (creada por él)" in rows["canvas-shows-day"]
    assert "custom" not in rows["musica"]


def test_the_video_cards_own_catalogue_is_not_this_one():
    assert runtime.identify("vuelve al catálogo")["system"] is None


def test_the_provider_and_its_probe_route_the_surface_to_the_panel():
    """Source anchors, because the branch lives in the middle of the provider's streaming loop: a named surface
    that is a TAB of the wall is forwarded through ONE reader (`panel_canon.wall_tab_for`) in both channels."""
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    assert "elif _wall_tab_for(_sys, text):" in prov
    assert 'emit("panel", "open", extra={"tab": _wall_tab_for(_sys, text), "src": "flash"})' in prov
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert 'f"panel:{_wall_tab_for(_sys, text)}" if _wall_tab_for(_sys, text) else "clarify"' in probe


def test_a_promise_to_open_the_tab_with_no_tool_opens_it():
    """Measured on the live engine after F1: «Te abro el panel de apps, que es donde salen los widgets que
    tienes» with NO tool call. The promise backstop only knew CARDS; a named wall tab now opens too — in the
    provider and in its mirror."""
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    seg = prov.split("elif _router.looks_like_show_strict(_op_text):")[1].split("elif _router.promises_music")[0]
    assert "_wall_tab_for(_identify_system(_op_text), _op_text)" in seg
    assert 'emit("panel", "open", extra={"tab": _wtab, "src": "flash"})' in seg
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    pseg = probe.split("elif _routerc.looks_like_show_strict(text):")[1].split("elif _routerc.promises_music")[0]
    assert 'action = f"panel:{_wtab}"' in pseg


@pytest.mark.parametrize("sid,phrase,tab", [
    ("apps", "O los widgets. Ábreme esa lista.", "apps"),
    ("apps", "Vale, ábreme la lista de widgets customizados.", "apps-custom"),
    ("chat", "abre el chat", "chat"), ("config", "abre los ajustes", ""), (None, "hola", ""),
])
def test_only_a_tab_of_the_wall_becomes_a_panel_event(sid, phrase, tab):
    from nucleo.flash.panel_canon import wall_tab_for
    assert wall_tab_for(sid, phrase) == tab


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


# ── the lane: an order that NAMES the tab opens it without the model ──────────────────────────────────────
# Measured after F1 with a clean window per phrase, three rounds of his six phrases: `show_panel` 10-13 of 18.
# The rest refused, promised with no tool, or spent a worker listing what the tab shows. The name decides now.
@pytest.mark.parametrize("phrase,tab", [
    ("Enséñame el catálogo de aplicaciones.", "apps"), ("Vale, enséñame el catálogo de widgets.", "apps"),
    ("Vale, ábreme la lista de widgets customizados.", "apps-custom"), ("O los widgets. Ábreme esa lista.", "apps"),
    ("Ábreme la lista de apps", "apps"), ("Johnny, ábreme las apps", "apps"),
    ("enséñame mis widgets personalizados", "apps-custom"),
])
def test_an_order_that_names_the_tab_is_decided_by_the_name(phrase, tab):
    from nucleo.flash.wall_lane import named_wall_tab
    assert named_wall_tab(phrase) == tab


@pytest.mark.parametrize("phrase", [
    "¿Qué APPs tengo customizadas?",          # a question: the model answers it, from its own catalogue
    "abre la aplicación de música", "ábreme el vídeo", "ábreme whatsapp", "abre el widget de música",
    "cierra las apps", "hazme un widget de recetas", "crea una app de notas", "no me abras las apps",
])
def test_the_lane_leaves_everything_else_to_the_model(phrase):
    from nucleo.flash.wall_lane import named_wall_tab
    assert named_wall_tab(phrase) == "", phrase


def test_the_voice_lane_opens_the_tab_and_records_the_exchange():
    import asyncio
    from voice.engine.llm.providers import fast_lane

    class _Brain:
        _window: list = []
        _acc = None

    events = []
    brain = _Brain()
    brain._window = []
    real = fast_lane._speak_ack

    async def _no_mouth(_b):
        return None
    fast_lane._speak_ack = _no_mouth
    try:
        took = asyncio.run(fast_lane.wall_tab(brain, "Vale, ábreme la lista de widgets customizados.",
                                              lambda *a, **k: events.append((a, k)), first_turn=False, window_max=20))
        missed = asyncio.run(fast_lane.wall_tab(brain, "¿Qué APPs tengo customizadas?",
                                                lambda *a, **k: events.append((a, k)), first_turn=False, window_max=20))
    finally:
        fast_lane._speak_ack = real
    assert took is True and missed is False
    panel = [k for a, k in events if a[:2] == ("panel", "open")]
    assert panel == [{"extra": {"tab": "apps-custom", "src": "flash"}}], events
    assert brain._window[-1] == {"role": "assistant", "content": "[panel:apps-custom]"}


def test_both_channels_try_the_lane_before_the_model():
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    lanes = prov.split("from voice.engine.llm.providers import fast_lane as _fast_lane")[1].split("return")[0]
    assert "_fast_lane.wall_tab(brain, text, emit" in lanes
    probe = (ENGINE / "nucleo/flash/probe_actionmap.py").read_text(encoding="utf-8")
    chain = probe.split("def try_fast_lanes")[1].split("\ndef ")[0]
    assert "try_wall_tab(text" in chain
