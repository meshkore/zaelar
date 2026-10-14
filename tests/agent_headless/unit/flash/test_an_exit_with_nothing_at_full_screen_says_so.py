"""Node 2.717 — «Exit full screen» with NO card at full screen is answered as that, never «Done.».

`video-exit-fullscreen-unnamed__us` (2026-10-14, 2/5): an empty canvas in every turn, `fullscreen_widget(mode=off)`
resolved no card, the turn became `canvas:unfullscreen:` with an empty target and the reply was «Done.». The fact is
the engine's: no target, no `maximized_widget`, no full screen his own order left (`canvas_focus`).

Disarm: make `nothing_at_full_screen` return False → the replacement tests go red; drop the `maximized_widget`
check → the «a card IS at full screen» test goes red.
"""
from __future__ import annotations

import pytest

from i18n import langs
from nucleo import canvas_focus
from nucleo.flash import fullscreen_nothing as FN


@pytest.fixture
def canvas(monkeypatch):
    from memory import api as memapi
    st = {"maximized_widget": ""}
    monkeypatch.setattr(memapi, "state", lambda *a, **k: dict(st))
    canvas_focus._reset()
    yield st
    canvas_focus._reset()


def test_a_bare_ack_over_an_exit_that_found_nothing_says_so(canvas):
    assert FN.honest("Done.", "canvas:unfullscreen:", lang=langs.spec("en")) == \
        "Nothing is at full screen right now, so there was nothing to exit."
    assert FN.honest("", "canvas:unfullscreen:", lang=langs.spec("es")).startswith("No hay ninguna tarjeta a pantalla completa")


def test_a_card_at_full_screen_keeps_the_ack(canvas):
    canvas["maximized_widget"] = "youtube"
    assert FN.honest("Done.", "canvas:unfullscreen:", lang=langs.spec("en")) == "Done."


def test_a_full_screen_his_order_left_keeps_the_ack(canvas):
    canvas_focus.note("widget", "fullscreen", extra={"id": "youtube", "src": "flash"})
    assert FN.honest("Done.", "canvas:unfullscreen:", lang=langs.spec("en")) == "Done."


def test_a_named_target_or_another_action_is_left_alone(canvas):
    assert FN.honest("Done.", "canvas:unfullscreen:youtube", lang=langs.spec("en")) == "Done."
    assert FN.honest("Done.", "canvas:show:youtube", lang=langs.spec("en")) == "Done."


def test_a_reply_with_content_is_left_alone(canvas):
    reply = "There's nothing in full screen right now — your canvas is empty."
    assert FN.honest(reply, "canvas:unfullscreen:", lang=langs.spec("en")) == reply


def test_the_text_channel_is_wired():
    from pathlib import Path
    probe = (Path(__file__).resolve().parents[4] / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert "_fsn.honest(" in probe
