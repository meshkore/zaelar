"""The first words go out at once; a second pass that can only confirm or correct them never holds them (V2-831 R5b).

Demo sandbox build 86, C2: the first pass had «Your afternoon opens up at 4…» at ~2 s. The words-after-data pass,
told what was already said, could only answer SKIP or a correction. It spent ~11 s before its first token and said
SKIP, and the turn (its reply event, the wall) waited for it until 12.7 s, after his next sentence. Its slow verdict
then blamed «PROMPT GRANDE: 19216 tok», which was the first pass's prompt, not the pass that took the time.

Four facts are proven here, for any confirm-or-correct pass:
  · the turn's speak returns before the pass does (the first words close the turn);
  · a correction still lands as a follow-up, and a SKIP or a repeat stays silent;
  · the typed channel, whose one reply is the whole answer, keeps the pass inline;
  · `turn_perf` measures second passes apart and names the one that took the time.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SAID = "Your afternoon opens up at 4, so 4:00 to 4:45 works — want me to send Rowan a message proposing it?"


class _SlowClient:
    """A provider that waits `delay` before its first token, then streams `reply` (C2's shape: long TTFT, short text)."""
    reply, delay = "SKIP", 0.3

    def stream(self, messages, *, spec=None, max_tokens=None, metrics=None, **_k):
        async def _gen():
            await asyncio.sleep(type(self).delay)
            if metrics is not None:
                metrics.update(ttft_ms=int(type(self).delay * 1000), prompt_tokens=700)
            for piece in type(self).reply.split(" "):
                yield piece + " "
        return _gen()


@pytest.fixture
def world(monkeypatch):
    """The fake provider, a captured delivery and emit, and NO typed collector (a live session can take a later line)."""
    import nucleo.llm.fast_client as fc
    from voice import proactive
    from nucleo.flash import turn_perf
    monkeypatch.setattr(fc, "FastClient", _SlowClient)
    told, events = [], []

    from nucleo.flash import follow_up_pass
    monkeypatch.setattr(follow_up_pass, "deliver", told.append)   # how it is delivered: R12's test
    tok = proactive._TURN_SPEAKER.set(None)
    turn_perf.take_passes()
    yield {"told": told, "events": events, "emit": lambda *a, **k: events.append((a, k))}
    proactive._TURN_SPEAKER.reset(tok)


def _run_detached(w, reply: str, delay: float = 0.3):
    from nucleo.flash import follow_up_pass as fup
    _SlowClient.reply, _SlowClient.delay = reply, delay

    async def _go():
        t0 = time.monotonic()
        detached = fup.detach("SYS", "user", SAID, None, 220, "op answer compose", w["emit"])
        returned_ms = (time.monotonic() - t0) * 1000
        tasks = list(fup._LIVE)
        if tasks:
            await asyncio.gather(*tasks)
        return detached, returned_ms
    return asyncio.run(_go())


def test_the_first_words_are_out_before_the_pass_returns(world):
    detached, returned_ms = _run_detached(world, "SKIP", delay=0.3)
    assert detached, "a confirm-or-correct pass after words already said must not run inside the turn"
    assert returned_ms < 100, f"the turn waited {returned_ms:.0f} ms on a pass that only confirms"
    labels = [a[1] for a, _ in world["events"]]
    assert any("primeras palabras entregadas" in x for x in labels) and any("SKIP" in x for x in labels)
    assert world["told"] == [], "a SKIP is silence"


def test_a_correction_still_lands_as_a_follow_up(world):
    detached, _ = _run_detached(world, "Actually the 4:00 slot is taken; 4:30 to 5:15 is free.", delay=0.05)
    assert detached and world["told"] == ["Actually the 4:00 slot is taken; 4:30 to 5:15 is free."]


def test_a_repeat_of_what_was_said_is_silence_too(world):
    _run_detached(world, SAID, delay=0.01)
    assert world["told"] == []


def test_the_typed_channel_keeps_the_pass_inline(world):
    """Its one reply is the whole answer: there is no later line to deliver a correction into."""
    from nucleo.flash import follow_up_pass as fup
    from voice import proactive
    tok = proactive._TURN_SPEAKER.set(lambda line: None)
    try:
        assert fup.detach("SYS", "user", SAID, None, 220, "x", world["emit"]) is False
    finally:
        proactive._TURN_SPEAKER.reset(tok)
    assert fup.detach("SYS", "user", "", None, 220, "x", world["emit"]) is False, "nothing said: the pass IS the answer"


def test_the_turn_wires_the_door_to_the_follow_up():
    """The provider's `speak` hands a confirm-or-correct pass to `follow_up_pass.detach`, and every inline pass
    streams through `measured`; the op-answer door asks for it."""
    src = (ROOT / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    assert "if follow_up and _fup.detach(sys2, user_text, _said, spec, max_tokens, what, emit):" in src
    assert "_fup.measured(FastClient(), sys2, user_text, spec, max_tokens, what)" in src
    door = (ROOT / "nucleo/flash/post_stream_acts.py").read_text("utf-8")
    assert 'await speak(_sys, _op_text, 220, "op answer compose", follow_up=True)' in door


def test_perf_measures_the_second_pass_apart(world):
    """C2's own numbers: the first pass 984 ms TTFT + 936 ms generating over 19 216 tokens, the second ~11 s."""
    from nucleo.flash import follow_up_pass as fup, turn_perf
    _SlowClient.reply, _SlowClient.delay = "Four works.", 0.02

    async def _inline():
        async for _ in fup.measured(_SlowClient(), "SYS", "user", None, 220, "op answer compose"):
            pass
    asyncio.run(_inline())
    passes = turn_perf.take_passes()
    assert passes and passes[0]["what"] == "op answer compose" and passes[0]["ttft_ms"] == 20 and not passes[0]["detached"]
    c2 = {"total_ms": 12627, "ttft_ms": 984, "gen_ms": 936, "prompt_tokens": 19216, "tok_per_s": 139.9,
          "sz_resources": 26793, "second_passes": [{"what": "op answer compose", "ms": 10965, "prompt_tokens": 748,
                                                    "ttft_ms": 10960, "detached": False}]}
    v = turn_perf.verdict(c2)
    assert v["cause"] == "segundo_pase" and "PROMPT GRANDE" not in v["label"], v["label"]
    assert "op answer compose" in v["label"] and "1er pase 1662 ms" in v["label"] and v["second_ms"] == 10965
    # without a second pass the first-pass diagnosis is untouched
    assert turn_perf.verdict({**c2, "second_passes": []})["cause"] == "prompt"


def test_a_detached_pass_reports_itself(world):
    _run_detached(world, "SKIP", delay=0.02)
    perf = [k["extra"] for a, k in world["events"] if a and a[0] == "perf"]
    assert perf and perf[-1]["detached"] and perf[-1]["what"] == "op answer compose" and perf[-1]["ttft_ms"] == 20
    from nucleo.flash import turn_perf
    assert turn_perf.take_passes() == [], "a detached pass is not the turn's: the turn did not wait on it"
