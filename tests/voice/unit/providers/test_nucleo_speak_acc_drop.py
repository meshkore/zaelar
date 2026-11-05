"""`_speak_acc_drop` — the gap valve's spoken acknowledgment (V2-096) upgraded with a judge check (V2-102):
`Accumulator`'s 25s gap valve discards a stale fragment chain when the operator went quiet longer than
expected. Before this, the discard always got the same generic "sorry, I missed that" notice — still a silent
loss of INTENT, just an acknowledged one. Now the judge gets one more look at what's being thrown away before
`_speak_acc_drop` decides what to say: a genuinely complete or clarification-worthy request shouldn't get the
same shrug as real gibberish just because the operator paused too long.

See `voice/engine/llm/providers/nucleo.py::_speak_acc_drop`.
"""
from __future__ import annotations

import asyncio

import pytest

from voice import proactive
from voice.engine.llm.providers import nucleo as nucleo_provider


@pytest.fixture(autouse=True)
def _speaker():
    """A fake live speaker, capturing what got said — same registration contract a real LiveKit session uses."""
    spoken = []

    async def _speak(text: str) -> None:
        spoken.append(text)

    proactive.register_speaker(_speak)
    yield spoken
    proactive.clear_speaker(_speak)


def _run(dropped: str) -> None:
    asyncio.run(nucleo_provider._speak_acc_drop(dropped))


def test_no_live_speaker_is_a_noop(monkeypatch):
    proactive.clear_speaker(None)   # force "no session" (probe/text channel)
    from nucleo.flash import segmenter

    async def _must_not_be_called(text):
        raise AssertionError("no live speaker — must not even consult the judge")
    monkeypatch.setattr(segmenter, "judge", _must_not_be_called)
    _run("algo que se perdió")   # must not raise


def test_never_talks_over_the_operator(monkeypatch, _speaker):
    monkeypatch.setattr(proactive, "user_speaking", lambda: True)
    _run("algo que se perdió")
    assert _speaker == []


def test_judge_says_ASK_speaks_the_clarifying_question_instead_of_the_generic_notice(monkeypatch, _speaker):
    from nucleo.flash import segmenter

    async def _fake_judge(text):
        return "ask", "¿Seguías queriendo que buscara vuelos a Londres?"
    monkeypatch.setattr(segmenter, "judge", _fake_judge)
    _run("busca vuelos a Londres para el finde")
    assert _speaker == ["¿Seguías queriendo que buscara vuelos a Londres?"]


def test_judge_says_COMPLETE_speaks_the_generic_notice(monkeypatch, _speaker):
    """COMPLETE can't safely re-dispatch a full turn from this out-of-band path (no live turn context): the
    operator gets an immediate spoken signal that something happened (V2-851 F5: no note rides his next turn)."""
    from nucleo.flash import segmenter

    async def _fake_judge(text):
        return "complete", ""
    monkeypatch.setattr(segmenter, "judge", _fake_judge)
    from voice.engine.core import langs

    _run("dame los datos personales que conoces de mi")
    assert _speaker == [langs.current_language().acc_fragment_dropped]


def test_judge_says_INCOMPLETE_keeps_the_plain_generic_notice(monkeypatch, _speaker):
    from nucleo.flash import segmenter

    async def _fake_judge(text):
        return "incomplete", ""
    monkeypatch.setattr(segmenter, "judge", _fake_judge)
    from voice.engine.core import langs

    _run("y ponerlo en la")
    assert _speaker == [langs.current_language().acc_fragment_dropped]


def test_a_broken_judge_falls_back_to_the_plain_notice_same_as_before_V2_102(monkeypatch, _speaker):
    from nucleo.flash import segmenter
    from voice.engine.core import langs

    async def _boom(text):
        raise RuntimeError("modelo caído")
    monkeypatch.setattr(segmenter, "judge", _boom)
    _run("algo que se perdió")
    assert _speaker == [langs.current_language().acc_fragment_dropped]
