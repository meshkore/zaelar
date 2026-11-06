"""No model runs after a turn's main stream (V2-851 F5, target of §13: model re-runs after the stream = 0).

Measured on 14 days of real sessions before F5 (§15a): 15 % of traces ran the model again after the reply streamed —
`jev reply-promise` 47, a second reply on the same trace 34, `jev rename` 19, the late catalogue 11, second passes 6.
F5 took them out: the second trip (`need_capability`), the deliberate look of an unreadable turn, the hollow-turn
repairs (a bare «Done.» to a question, an empty wait, a mute cover, a promise to look), the answer composed from
state, the detached confirm-or-correct pass, the write harness's `spec.infer`, the late catalogue and the rename trip.

ONE door test: a whole turn, driven through the one pipeline (the typed channel runs it), with a stubbed model that
counts every call — the fast client's streams and completions and every Jev trip — and marks when the main stream
ended. Whatever the turn does after that line, it may not call a model again. Cases are the shapes that used to
trigger a re-run. Disarm: put any one of the deleted passes back (e.g. a `FastClient().complete` in the close) → red.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.platform import turn_harness as H

LOG: list = []


def _client(reply: str, call: tuple | None = None):
    class _Counting:
        async def stream(self, messages, *, spec=None, tools=None, on_tool_call=None, metrics=None, **_k):
            LOG.append(("stream", bool(tools)))
            try:
                for piece in (reply[: len(reply) // 2], reply[len(reply) // 2:]):
                    if piece:
                        yield piece
            finally:
                if call and on_tool_call:
                    on_tool_call(*call)
                LOG.append(("stream_end", bool(tools)))

        async def complete(self, *_a, **_k):
            LOG.append(("complete", None))
            return ""

        def describe(self, spec=None) -> str:
            return "counting"
    return _Counting


@pytest.fixture
def turn(monkeypatch):
    with H.Isolated("es") as iso:
        from nucleo import jev
        from nucleo.cli import turn as t
        for name in ("choose_sync", "choose_many_sync", "ask_many"):
            real = getattr(jev, name, None)
            if real is not None:
                monkeypatch.setattr(jev, name, (lambda r, n: (lambda *a, **k: LOG.append(("jev", n)) or r(*a, **k)))(real, name))

        def _run(text, client):
            from nucleo.llm import fast_client
            iso._set(fast_client, "FastClient", client)
            LOG.clear()
            out = asyncio.run(t.run_turn(text, sid="no-rerun", ingest=False))
            return out, list(LOG)
        try:
            yield _run
        finally:
            t.reset("no-rerun")


def _after_the_main_stream(log: list) -> list:
    """Every model or Jev call logged after the FIRST main stream (one offered tools) ended."""
    ends = [i for i, (k, tools) in enumerate(log) if k == "stream_end" and tools]
    assert ends, f"the turn never streamed its main call: {log}"
    return [e for e in log[ends[0] + 1:] if e[0] in ("stream", "complete", "jev")]


@pytest.mark.parametrize("text,reply,call", [
    ("¿Tenemos alguna reserva en la agenda a algún restaurante?", "Hecho.", None),            # was: bare-ack repair
    ("¿Sigues con la tarea del viaje?", "Sigo con ella.", None),                              # was: continuity repair
    ("lo pon pa tipos como tú de Shakira", "", ("not_understood", {})),                       # was: deliberate look
    ("Let me know what's on my calendar", "Let me check your calendar now.", None),           # was: promise to look
])
def test_a_turn_calls_no_model_after_its_main_stream(turn, text, reply, call):
    out, log = turn(text, _client(reply, call))
    assert out.get("ok", True) is not False or out, out
    assert _after_the_main_stream(log) == [], f"a model ran after the main stream: {log}"
    assert sum(1 for k, tools in log if k == "stream" and tools) == 1, f"one main stream, never a second trip: {log}"


def test_the_counter_sees_a_rerun():
    """The disarm of the counter itself: a call after the line is reported."""
    assert _after_the_main_stream([("stream", True), ("stream_end", True), ("complete", None)]) == [("complete", None)]
