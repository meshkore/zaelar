"""«Tidy up the screen» lays out the cards ON SCREEN and leaves a minimized one in the rail.

Demo pass 2026-09-28 (C5b): over a calendar and a chat, the tidy brought back the errand sheet he had put away —
four cards where he asked for order — because both bulk gestures called `revealAll()` first. Bringing everything
back stays its own gesture (the rail's «show all»)."""
import re
from pathlib import Path

JS = (Path(__file__).resolve().parents[4] / "frontend/app/widgets/desktop.js").read_text("utf-8")


def _body(name):
    i = JS.index(f"\n  {name}(){{")
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
