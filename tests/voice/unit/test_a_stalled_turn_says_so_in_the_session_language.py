"""A turn the engine had to cut says so in the SESSION's language (demo pass 128, E1, 2026-10-14).

«check my email, did inworld send me something?» stalled on a provider blip and was cut; the line he heard was the
hard-coded «Uf, se me ha ido un momento. ¿Me lo repites?» in an English session — and the rest of the email block
fell after it. The fallback is the i18n `say_again`, the same line the mute backstop already uses.

Disarm: put the Spanish literal back in `turn_failure.say_the_turn_failed` → red.
"""
from __future__ import annotations

import asyncio

from i18n import langs


def test_a_stalled_turn_asks_again_in_english(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    from voice.engine.llm.providers import turn_failure
    sent = []
    out = asyncio.run(turn_failure.say_the_turn_failed(
        emit=lambda *a, **k: None, err_exc=None, err_text="", errored=True, llm_metrics={}, send=sent.append,
        spec=None, stalled=True))
    assert out == {"__return__": True}
    assert sent == [langs.spec("en").say_again], sent
