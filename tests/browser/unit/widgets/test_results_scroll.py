"""V2-591 — «haz scroll en la lista» moves the SHEET, and never a worker into the widget's code.

Measured in session 0e3a42d6 (2026-09-05): the scroll request got `results.tab` (nothing moved), then a
re-`present` + «Hecho.», then a Brain Worker was spawned to MODIFY the widget's CODE (it read widget.js and
data.py) until the operator stopped it — «No, no toques nada». Two faults: the sheet had no scroll surface
for the voice, and a UX request escalated to a code worker. This closes the first; with the capability
declared, the escalation loses its reason.

The scroller is CARD CHROME (ctx.top()'s own ownership rule), so the server stores a witnessed REQUEST
(push counter + expiry — the V2-540 pattern) and widget.js asks its HOST via the new ctx.scroll, which must
exist in BOTH hosts or it silently no-ops on the phone (the V2-124 contract).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[4]


@pytest.fixture()
def data(monkeypatch, tmp_path):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path), raising=False)
    from widgets.results import data as d
    return d


@pytest.mark.parametrize("spoken,expected", [
    ("baja", "down"), ("hacia abajo", "down"), ("", "down"), ("down", "down"),
    ("sube", "up"), ("hacia arriba", "up"), ("up", "up"),
    ("al principio", "top"), ("al inicio", "top"), ("top", "top"),
    ("al final", "bottom"), ("al fondo", "bottom"), ("bottom", "bottom"),
])
def test_the_spoken_direction_normalizes_to_four_values(data, spoken, expected):
    r = data.apply_action("scroll", {"where": spoken})
    assert r["ok"] and r["where"] == expected, (spoken, r)


def test_the_push_counter_advances_and_view_data_serves_it_fresh(data):
    data.apply_action("scroll", {"where": "baja"})
    v1 = data.view_data()
    assert v1["scroll"]["where"] == "down" and v1["scroll"]["n"] == 1
    data.apply_action("scroll", {"where": "baja"})
    v2 = data.view_data()
    assert v2["scroll"]["n"] == 2, "the counter is what lets the SAME order work twice (V2-540)"


def test_a_stale_request_expires_instead_of_moving_a_reader(data, monkeypatch):
    data.apply_action("scroll", {"where": "baja"})
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 300)
    assert "scroll" not in data.view_data(), \
        "a reload 5 minutes later must not re-apply an old order under the operator's eyes"


def test_both_hosts_implement_ctx_scroll():
    """A ctx member implemented in one host silently no-ops on the phone (V2-124's contract lesson)."""
    desk = (ENGINE / "frontend/app/widgets/desktop.js").read_text(encoding="utf-8")
    deck = (ENGINE / "frontend/mobile/app/shell/Deck.js").read_text(encoding="utf-8")
    for name, src in (("desktop", desk), ("deck", deck)):
        assert "scroll:" in src or "scroll: (" in src, f"the {name} host lost ctx.scroll"
        assert "scrollHeight" in src, f"the {name} host cannot reach the bottom"


def test_the_widget_applies_a_push_once_and_asks_its_host():
    src = (ENGINE / "widgets/results/widget.js").read_text(encoding="utf-8")
    assert "_hbScrollN" in src, "without the token guard, one order scrolls on EVERY refresh of a live sheet"
    assert "ctx.scroll(" in src, "the widget must ASK its host — the scroller is card chrome, not the widget's"


def test_the_manifest_declares_scroll_as_a_view():
    man = json.loads((ENGINE / "widgets/results/manifest.json").read_text(encoding="utf-8"))
    assert "scroll" in man["actions"], "undeclared = invisible to the brain (V2-540)"
    assert man["actions"]["scroll"].get("view") is True, \
        "«haz scroll» is a look-gesture: a pure show request must be allowed to run it (V2-545/V2-547)"
