"""An INSTRUCTION is never spoken: `[canvas:close:results]` is a directive, not a word (demo pass 109, S4, 2026-10-05).

«Done — closing it now.\n\n[canvas:close:results]» was read out loud and written on the wall. The model copied the
format of the action-map's own bookkeeping, which the window replayed to it as something Zaelar had SAID. Two
halves: the bookkeeping is recorded as words (what was said) with the act beside it, never as a bracketed line in
the assistant's mouth; and every text on its way to the TTS crosses one algorithmic filter that drops a directive
— a lowercase identifier with `:` segments in single brackets — whole or split across stream chunks. A bracketed
aside in prose is left to the stage-direction rule; a reply that is ONLY a directive is empty.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.mark.parametrize("raw,spoken", [
    ("Done — closing it now.\n\n[canvas:close:results]", "Done — closing it now."),
    ("[panel:tasks]", ""),
    ("Opening it [ canvas:show:agenda ] for you.", "Opening it for you."),
    ("Sure. [youtube:play_result:2]", "Sure."),
])
def test_a_directive_is_dropped_from_what_is_said(raw, spoken):
    from voice import speech
    assert speech.sanitize(raw) == spoken
    assert "canvas:" not in speech.inline(raw) and "panel:" not in speech.inline(raw)


def test_prose_in_brackets_and_times_are_not_directives():
    from voice import speech
    assert speech.drop_directives("Meet at [12:15] tomorrow") == "Meet at [12:15] tomorrow"
    assert speech.drop_directives("It says [Note: bring ID]") == "It says [Note: bring ID]"


def test_a_directive_split_across_chunks_is_held_until_it_closes():
    from voice.tag_protocol import strip_tags
    spoken, held = strip_tags("Done — closing it now. [canv", lambda *_a: None, False)
    assert "[" not in spoken and held.startswith("[canv")
    spoken2, held2 = strip_tags(held + "as:close:results]", lambda *_a: None, True)
    from voice import speech
    assert speech.sanitize(spoken2 + held2) == ""


def test_the_tts_door_filters_whatever_reaches_it():
    from voice.engine.speech import say_numbers

    async def chunks():
        for c in ("Closed it. [can", "vas:close:", "results]"):
            yield c

    async def collect():
        return "".join([x async for x in say_numbers.stream(chunks(), "en")])
    out = asyncio.run(collect())
    assert "canvas" not in out and out.strip() == "Closed it."


def test_the_action_map_records_words_not_a_bracketed_line(monkeypatch):
    from voice.engine.llm.providers import fast_lane
    src = open(fast_lane.__file__, encoding="utf-8").read()
    assert '"a": f"[{_desc}]"' not in src and 'f"[panel:{tab}]"' not in src, \
        "the window replays the assistant's bookkeeping as speech — the model copies it"
