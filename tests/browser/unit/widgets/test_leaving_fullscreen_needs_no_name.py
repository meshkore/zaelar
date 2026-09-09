"""«Sal de pantalla completa» has an obvious object, and the model could not see it (V2-609).

Measured live, session `4a492268`, 2026-09-07:

    18:54:02  OPERADOR  Ponme el video a pantalla completa.      → fullscreen_widget → maximize ✓
    18:54:27  OPERADOR  Sal de pantalla completa.
    18:54:29  ZAELAR    Hecho.                                   ← NO tool call at all
    18:54:36  OPERADOR  Quita la pantalla completa del vídeo.    → fullscreen_widget → exits ✓

The operator's reading is the correct one: one card was at full screen and practically nothing else was
open, so the target was not ambiguous — it was *obvious*. Three things were true at once and only the
third is a real defect:

  * `maximize()` IS a proper toggle, so the second phrasing left full screen correctly. Not the bug.
  * `attention.mentions_fullscreen` correctly stopped the close-backstop from closing the whole widget
    (V2-600). Not the bug.
  * `fullscreen_widget` REQUIRED `widget_id`, described as «the widget to ENLARGE», and the sentence names
    no widget. With nothing legal to pass — inventing an id is forbidden (V2-026) — the model called
    nothing and confabulated success. The engine's own friction detector logged «data-op fantasma» in the
    same second and was in cooldown, so nobody was told.

The fix is the V2-540/V2-603 lesson once more: the canvas KNEW which card was at full screen and never said
so. A verb whose object the system can see and the model cannot is a verb the model declines to use.
"""
import re
from pathlib import Path

import pytest

from memory import api as memory
from nucleo.flash import router_catalog, show_target
from widgets import brief

FRONTEND = Path(__file__).resolve().parents[4] / "frontend"


@pytest.fixture
def canvas(monkeypatch):
    """A canvas state we control: `state()` is the seam both channels and the prompt already read."""
    st = {"open_widgets": ["youtube", "agenda"], "recent_widgets": [], "maximized_widget": ""}
    monkeypatch.setattr(memory, "state", lambda: dict(st))
    return st


# ── the target resolves without a name ────────────────────────────────────────────────────────────────────

def test_with_no_name_the_target_is_the_card_that_is_at_full_screen(canvas):
    canvas["maximized_widget"] = "youtube"
    assert show_target.fullscreen_target("", "sal de pantalla completa") == "youtube"


def test_a_name_the_operator_gives_still_wins(canvas):
    canvas["maximized_widget"] = "youtube"
    assert show_target.fullscreen_target("agenda", "pon la agenda a pantalla completa") == "agenda"


@pytest.mark.parametrize("opened", [["youtube", "agenda"], ["youtube"]])
def test_leaving_full_screen_when_nothing_is_maximized_does_NOT_pick_a_widget(canvas, opened):
    """The dangerous shape, and the ONE-widget case is the one that matters: that is the operator's real
    situation, and it is where a «the only thing open must be it» fallback looks most reasonable. It is not.
    `fullscreen_widget` is a TOGGLE, so resolving a target when nothing is at full screen would put that card
    INTO full screen — the exact opposite of the order he gave. Resolving to nothing is the honest answer,
    and the caller asks instead of acting.

    (Caught by a disarm: the first version of this test only opened TWO widgets, so a single-widget fallback
    slipped straight through it.)"""
    canvas["open_widgets"] = opened
    canvas["maximized_widget"] = ""
    assert show_target.fullscreen_target("", "sal de pantalla completa") == ""


def test_a_natural_name_still_resolves_through_identify(canvas):
    """Narrowing an empty argument must not cost the useful half: when the model DOES name something, the
    name is resolved with the same open>recent>catalogue precedence as every other widget order."""
    canvas["maximized_widget"] = ""
    assert show_target.fullscreen_target("el vídeo", "ponlo a pantalla completa") == "youtube"


def test_a_name_that_resolves_to_nothing_asks_instead_of_guessing(canvas):
    canvas["maximized_widget"] = "youtube"
    assert show_target.fullscreen_target("el widget de contabilidad fiscal", "") == ""


def test_an_instance_card_answers_by_its_base_id(canvas):
    canvas["maximized_widget"] = "results"
    canvas["open_widgets"] = ["results"]
    assert show_target.fullscreen_target("", "quítala") == "results"


# ── the tool the model is offered ─────────────────────────────────────────────────────────────────────────

def _fullscreen_tool() -> dict:
    tools = getattr(router_catalog, "TOOLS", None) or getattr(router_catalog, "CATALOG", None) or []
    hit = next((t for t in tools if (t.get("function") or {}).get("name") == "fullscreen_widget"), None)
    assert hit, "fullscreen_widget desapareció del catálogo de tools"
    return hit["function"]


def test_widget_id_is_not_required_so_an_exit_order_has_a_legal_call():
    """The whole defect in one assertion. With `widget_id` required and no widget named, the only legal
    moves were to invent an id (forbidden) or to call nothing — and it called nothing."""
    fn = _fullscreen_tool()
    assert "widget_id" not in (fn["parameters"].get("required") or []), \
        "un argumento obligatorio que la frase no puede rellenar es una tool que el modelo NO llamará"


def test_the_tool_says_the_exit_needs_no_name_and_is_not_described_only_as_enlarging():
    """The description said «el widget a AMPLIAR» — one-directional prose on a two-directional toggle,
    which gives a model reading it a second reason to decline on an exit order."""
    fn = _fullscreen_tool()
    blob = (fn["description"] + " " + fn["parameters"]["properties"]["widget_id"]["description"]).lower()
    assert "pantalla completa" in blob
    assert "vacío" in blob or "vacio" in blob, "no dice que pueda llamarse SIN nombre"
    assert "a ampliar" not in blob, "la descripción del argumento vuelve a ser solo de ida"


# ── the fact the model was never told ─────────────────────────────────────────────────────────────────────

def test_the_prompt_says_which_card_is_at_full_screen(canvas):
    canvas["maximized_widget"] = "youtube"
    out = brief.for_prompt(["youtube", "agenda"])
    row = next((l for l in out.split("\n") if l.startswith("- youtube ")), "")
    assert "PANTALLA COMPLETA ahora" in row, "el canvas lo sabe y el prompt no lo dice"
    assert "fullscreen_widget" in row, "decir el hecho sin nombrar la salida deja al modelo adivinando"


def test_the_prompt_says_nothing_when_nothing_is_at_full_screen(canvas):
    canvas["maximized_widget"] = ""
    assert "PANTALLA COMPLETA ahora" not in brief.for_prompt(["youtube", "agenda"])


def test_the_mark_lands_on_the_maximized_card_and_not_on_its_neighbour(canvas):
    canvas["maximized_widget"] = "agenda"
    out = brief.for_prompt(["youtube", "agenda"])
    assert "PANTALLA COMPLETA ahora" in next(l for l in out.split("\n") if l.startswith("- agenda "))
    assert "PANTALLA COMPLETA ahora" not in next(l for l in out.split("\n") if l.startswith("- youtube "))


# ── the canvas reports it, and the server keeps it ────────────────────────────────────────────────────────

def test_the_canvas_reports_which_card_is_maximized():
    """`_restore` is the maximize marker and it already rode nowhere. The report that travels on every
    `_persist()` carried `min` and not `max` — the one piece of canvas state the server could not see."""
    src = (FRONTEND / "app" / "widgets" / "desktop.js").read_text(encoding="utf-8")
    layout = src[src.index("_layout(){"):src.index("_persist(){")]
    layout = "\n".join(re.sub(r"//.*$", "", ln) for ln in layout.split("\n"))
    assert re.search(r"max\s*:\s*r\s*\?", layout), "el canvas no informa de cuál está a pantalla completa"


def test_the_server_stores_the_maximized_card_from_the_canvas_report(monkeypatch):
    from server import voice_api
    written = {}
    monkeypatch.setattr(memory, "set_state", lambda d: written.update(d))
    monkeypatch.setattr(memory, "state", lambda: {"open_widgets": []})
    monkeypatch.setattr(memory, "note_widgets_used", lambda *a, **k: None)
    monkeypatch.setattr(memory, "kv_set", lambda *a, **k: None)
    import asyncio
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(voice_api.canvas_state({
        "open": ["youtube", "agenda"],
        "layout": [{"id": "agenda", "max": 0}, {"id": "youtube::t2", "max": 1}],
    }))
    assert written.get("maximized_widget") == "youtube", "la instancia se normaliza a su id base, como el resto"
    assert written.get("open_widgets") == ["youtube", "agenda"]


def test_nothing_maximized_is_reported_as_nothing(monkeypatch):
    from server import voice_api
    written = {}
    monkeypatch.setattr(memory, "set_state", lambda d: written.update(d))
    monkeypatch.setattr(memory, "state", lambda: {"open_widgets": []})
    monkeypatch.setattr(memory, "note_widgets_used", lambda *a, **k: None)
    monkeypatch.setattr(memory, "kv_set", lambda *a, **k: None)
    import asyncio
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(voice_api.canvas_state({
        "open": ["youtube"], "layout": [{"id": "youtube", "max": 0}]}))
    assert written.get("maximized_widget") == ""


# ── one decision, both channels ───────────────────────────────────────────────────────────────────────────

def test_both_channels_resolve_the_target_through_the_same_function():
    """The probe is a PARALLEL implementation of the voice path on purpose, and that is exactly how the two
    drift. Both must call `show_target.fullscreen_target` — a second copy here would mean the probe reports
    a decision the voice does not take (the trap V2-252 exists for)."""
    root = Path(__file__).resolve().parents[4]
    voice = (root / "voice" / "engine" / "llm" / "providers" / "nucleo.py").read_text(encoding="utf-8")
    probe = (root / "nucleo" / "flash" / "probe.py").read_text(encoding="utf-8")
    shared = (root / "nucleo" / "flash" / "show_target.py").read_text(encoding="utf-8")
    # V2-635 paid the provider's ratchet by moving the whole branch body into
    # `show_target.fullscreen_dispatch` — the CHANNEL is what this guard follows (V2-555): the voice
    # delegates to the dispatcher, the probe still resolves through fullscreen_target, and the shared
    # module is the only place the target decision lives.
    assert "fullscreen_dispatch(" in voice and "fullscreen_target(" in probe
    assert "fullscreen_target(" in shared.split("def fullscreen_dispatch", 1)[1], \
        "the dispatcher must resolve through the ONE target decision"
    for src, who in ((shared, "la voz (vía fullscreen_dispatch)"), (probe, "el probe")):
        seg = src[src.index("fullscreen_widget"):]
        seg = seg[:seg.index("fullscreen_target(")]
        assert "identify(" not in seg, f"{who} vuelve a resolver el id por su cuenta"
