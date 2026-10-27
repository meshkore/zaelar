"""The tester sees its own screen (2026-10-27).

The person a use case plays sits in front of the screen; the driver that plays them never saw it. Told «Ya está»
after the card really left full screen, the Spanish tester improvised «sigue igual» in two rounds running
(video-exit-fullscreen-unnamed__es), the agent then «fixed» a screen that was already right, and the judge scored
the product for the tester's guess. The round already knows the desktop (`canvas_now`, `card_seed.after_turn`):
it now tells the driver, once per change, as an aside the persona does not read out.
"""
from __future__ import annotations

from types import SimpleNamespace

from tests.use_cases.e2e.agent import driver as D
from tests.use_cases.e2e.agent.run import _screen_line


def _driver(locale="es"):
    d = D.Driver.__new__(D.Driver)
    d.scenario = SimpleNamespace(locale=locale)
    d.history = [{"role": "system", "content": "persona"}]
    return d


def test_the_line_names_the_open_card_and_which_one_is_at_full_screen():
    assert _screen_line(["youtube"], {"youtube"}, "es") == "abierto en la pantalla: youtube (a pantalla completa)"
    assert "nada está a pantalla completa" in _screen_line(["youtube"], set(), "es")
    assert _screen_line([], set(), "us") == "nothing is open on the screen"


def test_the_driver_is_told_once_per_change_and_never_reads_it_out():
    d = _driver()
    d.sees(_screen_line(["youtube"], {"youtube"}, "es"))
    d.sees(_screen_line(["youtube"], {"youtube"}, "es"))      # unchanged: not repeated
    d.sees(_screen_line(["youtube"], set(), "es"))
    notes = [m["content"] for m in d.history if "pantalla" in m["content"] and m["content"] != "persona"]
    assert len(notes) == 2, notes
    assert "a pantalla completa)" in notes[0] and "nada está a pantalla completa" in notes[1]
    assert all("no lo leas en voz alta" in n for n in notes)


def test_the_round_folds_the_seeded_card_in_before_the_first_line():
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/run.py").read_text()
    assert '_canvas_acts.append({"cat": "widget", "label": "show", "id": str(_seeded["card"]), "t_ms": 0})' in src
    assert "driver.sees(_screen_line(_canvas_said, _maxed, scenario.locale))" in src


def test_the_screen_rides_with_what_zaelar_just_said():
    """A trailing system aside was ignored by the drive model; the screen goes in the same message."""
    d = _driver()
    d.hears("Vale, hecho.")
    d.sees(_screen_line(["youtube"], set(), "es"))
    assert d.history[-1]["role"] == "user"
    assert d.history[-1]["content"].startswith("Vale, hecho.") and "nada está a pantalla completa" in d.history[-1]["content"]
