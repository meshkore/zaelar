"""A first run does not wear the previous install's browser state (V2-735).

The operator, on a freshly reset install: «cuando el sistema arranca, no quiero
que por defecto el orbe esté metido en la barra inferior. Quiero que el orbe esté
desplegado y que se vea el orbe grande con el pulso y todo… totalmente arrancado,
porque la voz tiene que empezar a sonar enseguida».

And by default it IS: `store.orbDock` defaults to "eye" and `store.powerOff` to
false. What he was looking at was the PREVIOUS install's `hb_orb_dock=bar` and
`hb_power_off=1` — a factory reset (V2-670) starts the AGENT over and cannot
reach localStorage, which is per-origin and survives everything the server can do
to itself.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("test_a_first_run_does_not_wear_the_previous_install.mjs")
MAIN = Path("frontend/app/main.js")
STORE = Path("frontend/app/core/store.js")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_takeover_wipes_what_is_ours_and_nothing_else():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_the_deployed_orb_and_a_live_voice_ARE_the_defaults():
    """Nothing in this fix changes what the product defaults to — the point is that a default is what a
    new operator should get. If either of these ever flips, the fix above is papering over it."""
    src = STORE.read_text(encoding="utf-8")
    assert 'localStorage.getItem("hb_orb_dock") === "bar" ? "bar" : "eye"' in src, (
        "the orb lives in the big eye cluster unless the operator moved it")
    assert 'localStorage.getItem("hb_power_off") === "1"' in src, (
        "the voice is ON unless the operator switched it off")


def test_the_takeover_runs_on_the_first_run_branch_and_stops_the_boot():
    """It has to sit exactly where the engine says «nobody has ever chosen a language», and the caller
    has to RETURN when it fires: the page is on its way out, and opening the language modal on a document
    that is being replaced is how a first run shows a flash of the wrong thing."""
    src = MAIN.read_text(encoding="utf-8")
    i_chosen = src.index('s.chosen !== false')
    i_take = src.index("firstRun.takeoverOnFirstRun(", i_chosen)
    i_open = src.index("store.setLangOnboardOpen(true)", i_chosen)
    assert i_chosen < i_take < i_open, "wipe first, then the picker"
    between = src[i_take:i_open]
    assert "return" in between, "a takeover must stop the boot: the page is going away"
