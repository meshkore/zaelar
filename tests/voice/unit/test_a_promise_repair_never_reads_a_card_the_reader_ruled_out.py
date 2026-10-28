"""A promise repair reads a card only when something NAMES it; when the catalogue reader is SURE no card is involved,
the reply's own words cannot overrule it (node 2.921).

Live, 2026-10-28 17:49 (T29): «I can't believe that, I just asked !!!!!!!» after a Dexter question; the reply promised
«let me just check it properly… which of your services…», the reader said `none` at 0.89, and the repair's last
fallback — the reply's words — matched a user widget called «canvas-shows-day» on «shows», read it, and appended
«today is Wednesday, October 28th… What exactly would you like to know about those days?».

Disarm: with `_card_the_catalogue_names` returning "" instead of «none», the first test goes red.
"""
from __future__ import annotations

import asyncio

from nucleo.flash import second_pass, widget_read


def test_a_sure_none_from_the_reader_ends_the_repair_before_the_replys_words(monkeypatch):
    async def none(_text, wait_s=3.0):
        return "none"
    monkeypatch.setattr(second_pass, "_card_the_catalogue_names", none)
    read = []
    monkeypatch.setattr(widget_read, "resolve", lambda arg, text="": read.append(text) or ("canvas-shows-day" if "shows" in text else None))
    out = asyncio.run(second_pass.promise_repair("I can't believe that, I just asked", "let me check which of your shows",
                                                 [], None, lambda *a, **k: None))
    assert out == "" and read == ["I can't believe that, I just asked"]   # the reply was never consulted


def test_a_named_card_is_still_read(monkeypatch):
    async def none(_text, wait_s=3.0):
        return ""
    monkeypatch.setattr(second_pass, "_card_the_catalogue_names", none)
    monkeypatch.setattr(widget_read, "resolve", lambda arg, text="": "agenda" if "calendar" in text else None)

    async def prepare(*a, **k):
        return "SYS"
    monkeypatch.setattr(widget_read, "prepare", prepare)

    async def collect(sys2, text, spec, max_tokens=220):
        return "Tomorrow you have the dentist at ten."
    monkeypatch.setattr(second_pass, "collect", collect)
    out = asyncio.run(second_pass.promise_repair("what do I have tomorrow", "let me pull up your calendar",
                                                 [], None, lambda *a, **k: None))
    assert "dentist" in out
