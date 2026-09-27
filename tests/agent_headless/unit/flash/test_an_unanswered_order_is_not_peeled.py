"""V2-776 D0 — words whose turn died BEFORE answering them are not peeled off as «already answered».

Session 3a9a082c, 2026-09-27 12:39, byte for byte from the timeline:

    12:39:32  «So open me a video.»            → act; its turn starts generating
    12:39:35  «Of the» arrives                  → that turn is cancelled, «superado por otro turno», unanswered
    12:39:36  offer «So open me a video. Of the» → ⏸ hold, acumulado «Of the»   ← the order was peeled off
    12:39:40  🧩 «Of the Madonna. Concert Some of them, I don't care.»

The model still called `play_video` (the kept window had the order), and the `video_without_order` guard read
the merged sentence, found no video in it and dropped the call. The operator had to say «video widget».
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.flash import accumulator as acc


@pytest.fixture
def held(monkeypatch):
    """Layer 2 says «incomplete» for a dangling tail, so this measures layer 1 and the assembly, never a model."""
    async def _judge(_t):
        return "incomplete", ""
    monkeypatch.setattr(acc, "_judge", _judge)
    monkeypatch.setenv("ZAELAR_JEV", "0")      # `continuation` asks Jev about a seam; never a live model here
    return acc.Accumulator()


def _offer(a, text, t):
    return asyncio.run(a.offer(text, now=t))


def _died(a, text):
    acc.unanswered_by(type("B", (), {"_acc": a})(), text)


def _replay(a, *, the_turn_died: bool):
    assert _offer(a, "So open me a video.", 100.0)[0] == "act"
    if the_turn_died:
        _died(a, "So open me a video.")
    action, text, _, _ = _offer(a, "So open me a video. Of the", 103.0)
    if the_turn_died:
        # Unanswered, the order is offered to the brain AGAIN (the tail waits as the buffer) — and he is still
        # talking, so that turn is cancelled too, before its first word.
        assert (action, text) == ("act", "So open me a video.")
        _died(a, "So open me a video.")
    else:
        assert action == "hold"
    return _offer(a, "So open me a video. Of the Madonna. Concert Some of them, I don't care.", 107.0)


def test_the_order_survives_when_its_turn_died_unanswered(held):
    action, merged, _, _ = _replay(held, the_turn_died=True)
    assert action == "act"
    assert "open me a video" in merged, f"the order was lost from the sentence: {merged!r}"


def test_an_answered_head_is_still_peeled(held):
    """V2-747's half stays true: when the head WAS answered, it is not answered a second time."""
    action, merged, _, _ = _replay(held, the_turn_died=False)
    assert action == "act"
    assert "open me a video" not in merged


def test_the_voice_provider_calls_it_where_a_turn_dies_unanswered():
    """The wiring, both doors: the pre-stream wrapper and the stream's own cancel handler (only when nothing
    had been said). A seam nobody calls is how this sentence lost its verb."""
    import inspect
    from voice.engine.llm.providers import nucleo
    src = inspect.getsource(nucleo)
    assert src.count("_acc_mod.unanswered_by(") == 2
    assert 'if not "".join(spoken):\n                _acc_mod.unanswered_by(brain, text)' in src
