"""Node 2.717 — «Exit full screen» with NO card at full screen is answered as that, never «Done.».

`video-exit-fullscreen-unnamed__us` (2026-10-14, 2/5): an empty canvas in every turn, `fullscreen_widget(mode=off)`
resolved no card, the turn became `canvas:unfullscreen:` with an empty target and the reply was «Done.». The fact is
the engine's: no target, no `maximized_widget`, no full screen his own order left (`canvas_focus`).

The old text channel patched the model's words after the fact (`fullscreen_nothing.honest`, a check on a content-free
reply). That is the class refactor2710-03 removes: the mouth says the verdict. Until then this stays an expected
failure, strict, so it goes red the day the 03 makes it pass.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(reason="refactor2710-03: the mouth speaks the verdict", strict=True)
def test_the_typed_turn_says_there_was_nothing_to_exit():
    """The whole turn (the voice turn, typed): an empty canvas, the model calls `fullscreen_widget(mode=off)` and says
    «Done.» — what he hears is that nothing was at full screen."""
    from tests.brain import harness as H
    case = {"id": "fsn-empty", "lang": "en", "phrase": "Exit full screen.", "source": "node 2.717",
            "screen": {"open": []}, "expect": "unfullscreen",
            "model": {"say": "Done.", "tools": [{"name": "fullscreen_widget", "args": {"mode": "off"}}]}}
    out = H.run_case(case)
    assert not out.error, out.error
    assert "Nothing is at full screen" in out.reply, (out.action, out.reply)
