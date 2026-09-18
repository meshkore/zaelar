"""fix01 · the third unanswered speech is not judged — session 6d19df41 went deaf on arrival.

Measured live: the cold-start judge returned `llm_ambient` on «Hey, Tony. Open my messages.»
(an explicit order), then on «Are you copying?» (a direct second-person check-in) — four turns
unanswered before «Hello?» got through. One discard may be room noise; speech that keeps coming
while nobody answers is the operator talking to a wall.

The gate counts consecutive discards (`note_ambient`, the single seam every drop goes through)
and after two of them the next cold turn is directed WITHOUT consulting the judge
(`unanswered_repeat`). A handled turn, a deliberate reset, or 60 s of silence ends the streak.
"""
from __future__ import annotations

import asyncio

import pytest

from voice import attention


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    attention.set_directed_judge(None)
    yield
    attention.reset()
    attention.set_directed_judge(None)


def _run(coro):
    return asyncio.run(coro)


async def _HOSTILE_JUDGE(text, context):
    return False  # the judge at its worst: always ambient


def test_two_unanswered_speeches_force_the_third_one_open():
    """The session replay: order dropped, check-in dropped, next speech goes through — the judge
    (injected hostile: False on everything) is never even asked."""
    attention.set_directed_judge(_HOSTILE_JUDGE)
    calls = {"n": 0}

    async def counting_judge(text, context):
        calls["n"] += 1
        return False

    attention.set_directed_judge(counting_judge)
    now = 1000.0
    assert not _run(attention.evaluate_content("Hey, Tony. Open my messages.",
                                               context="Hi Richard!", now=now)).directed
    attention.note_ambient("Hey, Tony. Open my messages.", now=now)
    assert not _run(attention.evaluate_content("Are you copying?",
                                               context="Hi Richard!", now=now + 10)).directed
    attention.note_ambient("Are you copying?", now=now + 10)
    v = _run(attention.evaluate_content("Do you copy?", context="Hi Richard!", now=now + 13))
    assert v.directed and v.reason == "unanswered_repeat"
    assert calls["n"] == 2, "the third turn must not consult the judge at all"


def test_one_discard_alone_still_asks_the_judge():
    attention.set_directed_judge(_HOSTILE_JUDGE)
    attention.note_ambient("some room noise", now=1000.0)
    v = _run(attention.evaluate_content("more room noise", context="hi", now=1010.0))
    assert not v.directed and v.reason == "llm_ambient"


def test_a_handled_turn_ends_the_streak():
    attention.set_directed_judge(_HOSTILE_JUDGE)
    attention.note_ambient("noise one", now=1000.0)
    attention.note_ambient("noise two", now=1010.0)
    attention.note_directed(now=1020.0)
    assert attention.unanswered_streak(1030.0) == 0


def test_stale_discards_do_not_accumulate():
    attention.set_directed_judge(_HOSTILE_JUDGE)
    attention.note_ambient("noise one", now=1000.0)
    attention.note_ambient("noise two", now=1010.0)
    v = _run(attention.evaluate_content("much later", context="hi", now=5000.0))
    assert not v.directed and v.reason == "llm_ambient"


def test_empty_discards_do_not_feed_the_streak():
    attention.note_ambient("", now=1000.0)
    attention.note_ambient("   ", now=1010.0)
    assert attention.unanswered_streak(1020.0) == 0


def test_a_deliberate_reset_ends_the_streak():
    attention.note_ambient("noise one", now=1000.0)
    attention.note_ambient("noise two", now=1010.0)
    attention.close_window(src="test")
    assert attention.unanswered_streak(1020.0) == 0
