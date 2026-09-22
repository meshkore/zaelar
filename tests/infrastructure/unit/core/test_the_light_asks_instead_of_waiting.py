#
# test_the_light_asks_instead_of_waiting.py — V2-750. Getting back to the titular, and getting the panel back
# to green without needing the operator to speak.
#
# THE MEASUREMENT (2026-09-22, his own engine). One voice turn failed at 12:21:02 — `Cerebro rápido caído —
# turno degradado`. At 12:27 the panel still read «deepseek-v4-pro · DeepSeek · no responde», while DeepSeek
# probed in that same minute answered `/models` 200, reported a $2.77 balance and completed a chat in 1.22 s.
# Six minutes of a red light over a healthy provider. His words: «el agente local en el browser me sigue
# marcando una alarma diciendo que no responde».
#
# CAUSE: many writers, ONE clearer. `health_state.record("llm", …)` is written by every path that sees a
# model fail; the only thing that ever cleared it was the first chunk of a successful VOICE turn. With no
# microphone open, nothing could repaint it before the 600 s TTL — and the next failure re-armed it.
#
# THE CADENCE IS HIS, verbatim: «haría comprobaciones de forma recursiva, en plan primero cada 10 segundos,
# luego cada 60 segundos, luego cada 3 minutos, hasta que consiguiéramos volver al principal».
#
import asyncio

import pytest

from nucleo.flash import titular_watch as tw


@pytest.fixture(autouse=True)
def _clean():
    from voice import health_state
    tw._state.update({"running": False, "step": 0, "last_probe": 0.0, "last_ok": 0.0, "probes": 0})
    health_state.clear("llm")
    yield
    tw._state.update({"running": False, "step": 0, "last_probe": 0.0, "last_ok": 0.0, "probes": 0})
    health_state.clear("llm")


# ── the ladder is the operator's ──────────────────────────────────────────────────────────────────────
def test_the_backoff_is_ten_seconds_then_a_minute_then_three():
    assert tw.BACKOFF_S == (10.0, 60.0, 180.0)


def test_it_steps_down_the_ladder_and_stops_at_the_bottom(monkeypatch):
    """«Hasta que consiguiéramos volver al principal» — it keeps asking forever, but a provider down for an
    hour is asked every three minutes, not every ten seconds."""
    monkeypatch.setattr(tw, "ailing", lambda: True)
    monkeypatch.setattr(tw, "_titular", lambda: {"name": "titular", "model": "m", "base_url": "u"})
    monkeypatch.setattr(tw, "probe", lambda tier: (False, "HTTP 500"))
    seen = []
    for _ in range(6):
        tw._state["last_probe"] = 0.0          # pretend the wait elapsed
        asyncio.run(tw._tick())
        seen.append(tw._state["step"])
    assert seen == [1, 2, 2, 2, 2, 2], seen


def test_it_waits_its_turn_instead_of_probing_every_tick(monkeypatch):
    """The loop ticks every few seconds; the PROBE costs a request against his account, so it may not ride
    the loop's rhythm."""
    monkeypatch.setattr(tw, "ailing", lambda: True)
    monkeypatch.setattr(tw, "_titular", lambda: {"name": "titular", "model": "m", "base_url": "u"})
    calls = []
    monkeypatch.setattr(tw, "probe", lambda tier: (calls.append(1), (False, "x"))[1])
    tw._state["last_probe"] = 0.0
    asyncio.run(tw._tick())
    asyncio.run(tw._tick())                     # immediately after: inside the 10 s wait
    assert len(calls) == 1, "it probed twice in a row — the backoff is not being honoured"


# ── what it is allowed to do ──────────────────────────────────────────────────────────────────────────
def test_a_good_probe_clears_the_light(monkeypatch):
    from voice import health_state
    health_state.record("llm", "outage", "un turno se cayó")
    assert health_state.get("llm")
    monkeypatch.setattr(tw, "ailing", lambda: True)
    monkeypatch.setattr(tw, "_titular", lambda: {"name": "titular", "model": "m", "base_url": "u"})
    monkeypatch.setattr(tw, "probe", lambda tier: (True, "200"))
    tw._state["last_probe"] = 0.0
    asyncio.run(tw._tick())
    assert health_state.get("llm") is None, "six minutes of red over a healthy provider is the whole defect"
    assert tw._state["step"] == 0, "recovery resets the ladder — the next outage starts at 10 s again"


def test_it_can_only_ever_turn_the_light_GREEN(monkeypatch):
    """⚠️ A prober that could CONDEMN a provider would be a second opinion competing with the real turns,
    and the real turns carry the actual prompt, tools and latency. A probe that says «fine» while every turn
    fails must lose — so it is not allowed to vote at all."""
    from voice import health_state
    monkeypatch.setattr(tw, "ailing", lambda: True)
    monkeypatch.setattr(tw, "_titular", lambda: {"name": "titular", "model": "m", "base_url": "u"})
    monkeypatch.setattr(tw, "probe", lambda tier: (False, "HTTP 503"))
    tw._state["last_probe"] = 0.0
    asyncio.run(tw._tick())
    assert health_state.get("llm") is None, "a failed probe must NOT light a lamp of its own"
    src = (tw.__file__ and open(tw.__file__, encoding="utf-8").read()) or ""
    body = src.split('"""', 2)[-1]
    assert "health_state.record" not in body, "this module may clear, never record"


def test_nothing_is_probed_while_everything_is_healthy(monkeypatch):
    """A healthy engine must cost ZERO requests. `ailing()` touches no network on purpose."""
    monkeypatch.setattr(tw, "ailing", lambda: False)
    monkeypatch.setattr(tw, "probe", lambda tier: pytest.fail("it probed a provider with nothing wrong"))
    tw._state["step"] = 2
    asyncio.run(tw._tick())
    assert tw._state["step"] == 0, "and it forgets the ladder, so the next outage starts at the top"


# ── the probe's own rule ──────────────────────────────────────────────────────────────────────────────
def test_a_200_with_an_EMPTY_body_counts_as_alive():
    """Measured 2026-09-22: `deepseek-v4-pro` answers 200 in 7.47 s with '' — a reasoner spending a small
    `max_tokens` budget on thinking. Reading the BODY would have this module condemn a healthy provider for
    answering the way it always answers. The question is «is anybody home», and a status line answers it."""
    src = open(tw.__file__, encoding="utf-8").read()
    fn = src.split("def probe(", 1)[1].split("\ndef ", 1)[0]
    assert "200 <= r.status < 300" in fn, "the verdict has to come from the STATUS, not the content"
    # …and it must not so much as READ the body. `content` appears in the REQUEST («"content": "ping"»,
    # `Content-Type`), so the thing to assert is that nothing parses the ANSWER.
    for reader in ("r.read()", "json.loads", "choices"):
        assert reader not in fn, f"the probe parses the reply ({reader}) — see the empty-200 measurement"


def test_a_rung_without_a_credential_is_not_probed():
    """«Sin credencial no es un escalón, es un espejismo» — and probing one would burn a request to be told
    401 forever."""
    ok, why = tw.probe({"name": "x", "model": "m", "base_url": "https://example.invalid", "env": ["NOPE_KEY"]})
    assert ok is False and "credencial" in why
