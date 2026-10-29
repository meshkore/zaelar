"""A follow-up a turn detaches is delivered right after THAT turn, the way its first words were (V2-831 T-19 R12).

Demo sandbox build 86, pass 2, M2 «what about the last month»: the first words said «switching it to the last
month»; the detached pass carried the answer («Over the last month Apple is at 343.83 USD, up 4.38%…») and handed
it to `proactive.notify`. Its ticket queue was held by an earlier say that never reported done, so the delivery
waited the queue's 180 s, gave up, and became a `[SISTEMA] Entrega proactiva pendiente` note that rode a turn 25
steps later («Done — the results are closed»). An answer the first words promised is the turn's own answer, not
an optional notice: it goes to the wall, the dialog window and the session's speaker at once, and is never parked.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.waiting import until

ANSWER = "Over the last month the stock is at 343.83 USD, up 4.38%."


@pytest.fixture
def session(monkeypatch):
    """A live session (a speaker), a WEDGED proactive queue (a ticket taken and never released — what an earlier
    say that never completes leaves behind), and spies on the wall, the dialog and the next-turn notes."""
    from nucleo.flash import dialog
    from voice import brain_notes, observer, proactive
    proactive._reset_queue_for_tests()
    proactive._take_ticket()                                   # held forever: every queued delivery waits behind it
    monkeypatch.setattr(proactive, "_QUEUE_MAX_WAIT", 1.5)     # a disarmed run degrades in seconds, not minutes
    got = {"said": [], "wall": [], "dialog": [], "notes": []}

    async def _speak(text):
        got["said"].append(text)
    monkeypatch.setattr(proactive, "_speaker", _speak)
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: got["wall"].append(k) if k.get("extra", {}).get("wall") else None)
    monkeypatch.setattr(dialog, "note_spoken", lambda text, about="": got["dialog"].append(text))
    monkeypatch.setattr(brain_notes, "push", lambda text, key="", ttl_s=0.0: got["notes"].append(text))
    yield got
    proactive._reset_queue_for_tests()


def _detached_correction():
    import nucleo.llm.fast_client as fc
    from nucleo.flash import follow_up_pass as fup

    class _Client:
        def stream(self, messages, **k):
            async def _gen():
                yield ANSWER
            return _gen()
    return fc, fup, _Client


def test_the_detached_answer_is_spoken_and_posted_with_its_turn(session, monkeypatch):
    fc, fup, client = _detached_correction()
    monkeypatch.setattr(fc, "FastClient", client)

    async def _go():
        assert fup.detach("SYS", "user", "— switching it to the last month for you.", None, 220, "op answer compose",
                          lambda *a, **k: None)
        await until(lambda: session["said"], "the follow-up to reach the session's speaker", timeout_s=1.0)
        await asyncio.gather(*list(fup._LIVE))
    asyncio.run(_go())
    assert session["said"] == [ANSWER] and session["wall"] and session["wall"][0]["text"] == ANSWER
    assert session["wall"][0]["role"] == "assistant" and session["dialog"] == [ANSWER]


def test_it_never_rides_on_a_later_turn(session, monkeypatch):
    fc, fup, client = _detached_correction()
    monkeypatch.setattr(fc, "FastClient", client)

    async def _go():
        fup.detach("SYS", "user", "— switching it to the last month for you.", None, 220, "op answer compose",
                   lambda *a, **k: None)
        await until(lambda: not fup._LIVE, "the detached pass to finish", timeout_s=3.0)
    asyncio.run(_go())
    assert session["notes"] == [], f"the answer was parked for the next turn: {session['notes']}"


def test_with_no_voice_the_wall_and_the_window_still_have_it(session, monkeypatch):
    from nucleo.flash import follow_up_pass as fup
    from voice import proactive
    monkeypatch.setattr(proactive, "_speaker", None)
    fup.deliver(ANSWER)
    assert session["wall"] and session["dialog"] == [ANSWER] and session["notes"] == []
