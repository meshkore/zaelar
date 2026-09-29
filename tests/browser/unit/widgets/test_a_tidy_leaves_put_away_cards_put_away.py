"""«Tidy up the screen» lays out the cards ON SCREEN and leaves a minimized one in the rail.

Demo pass 2026-09-28 (C5b): over a calendar and a chat, the tidy brought back the errand sheet he had put away —
four cards where he asked for order — because both bulk gestures called `revealAll()` first. Bringing everything
back stays its own gesture (the rail's «show all»)."""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parents[4] / "frontend/app/widgets/desktop.js").read_text("utf-8")


def _body(name):
    i = JS.index(f"\n  {name}(") if name == "_yieldBackground" else JS.index(f"\n  {name}(){{")
    return JS[i:JS.index("\n  }\n", i)]


def test_neither_tidy_brings_back_a_minimized_card():
    for g in ("arrange", "compact"):
        b = _body(g)
        assert "revealAll" not in b, f"{g}() un-minimizes the cards he put away"
        assert "this._onScreen()" in b, f"{g}() must lay out only what is on screen"


def test_on_screen_means_not_minimized():
    assert re.search(r"_onScreen\(\)\{[^}]*!c\.classList\.contains\(\"hb-minned\"\)", _body("_onScreen") + "}")


def test_show_all_is_still_a_gesture_of_its_own():
    rail = (Path(__file__).resolve().parents[4] / "frontend/app/components/WidgetRail.js").read_text("utf-8")
    assert "revealAll()" in rail


def test_showing_a_card_he_put_away_brings_it_back_but_a_workers_show_does_not():
    """full17 S1: «show me» on the minimized results sheet raised its z and left it hidden."""
    i = JS.index("\n  async show(rawId")
    body = JS[i:JS.index("\n  }\n", i)]
    assert re.search(r'if\(!background && w\.card\.classList\.contains\("hb-minned"\)\)\{\s*w\.card\.classList\.remove'
                     r'\("hb-minned"\)', body)


def test_a_card_he_asks_for_wins_the_space_over_a_background_sheet():
    """full21 Z1: «what's on tomorrow» brought the agenda up under the trip errand's sheet, 64% covered. A sheet a
    worker opened in the background tucks into the rail when an operator card needs its place; one he brought up
    himself is never moved."""
    i = JS.index("\n  async show(rawId")
    show = JS[i:JS.index("\n  }\n", i)]
    assert "card._bg = !!background;" in show
    assert "if(!background){ this._yieldBackground(card);" in show
    assert "w.card._bg = false;" in show, "his own show of a sheet makes it his"
    y = _body("_yieldBackground")
    assert "!c._bg" in y and 'c.classList.add("hb-minned")' in y and "0.2*" in y
