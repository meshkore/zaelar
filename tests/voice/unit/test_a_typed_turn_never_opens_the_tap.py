#
# test_a_typed_turn_never_opens_the_tap.py — V2-852 T01 (rule R1: text never opens the voice).
#
# Measured in session c8a307fd: wake-word mode, tap parked; he TYPED «yes.» and in the same 0.3 s the browser
# logged `grifo abierto` and the engine `audio input OPEN (STT)`; the room's «Finch.» and «No.» then ran as orders.
# The chain: the typed handler opened the voice window (`note_directed`), the gate emitted a DIRECTED `ambient`
# verdict, the client lit its ring from it and unparked the tap from the ring. A typed line is directed by its own
# fact — so it passes the gate, renews no window, and sends no `ambient` verdict for the ring to read.
import asyncio

import pytest

from voice import attention
from voice.engine.llm.providers import attention_turn


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("ZAELAR_ATTENTION", "ZAELAR_ATTENTION_WINDOW", "ZAELAR_WAKEWORDS"):
        monkeypatch.delenv(k, raising=False)
    attention.reset()
    attention.set_directed_judge(None)
    yield
    attention.reset()


def _typed_turn(line: str):
    """The typed door as it runs: the handler's stamp, then the gate on the same line (routing stubbed by the caller)."""
    from voice.engine.pipeline import agent_events
    events = []
    monkey_emit = lambda kind, label="", **kw: events.append((kind, label, kw))  # noqa: E731
    agent_events.receive_typed(line, _emit=monkey_emit, session=None)
    ok, _, _ = asyncio.run(attention_turn.judge(line, context="", emit=monkey_emit))
    return ok, events


@pytest.mark.parametrize("mode", ["smart", "wakeword"])
@pytest.mark.parametrize("line", ["yes.", "sí, sigue", "はい、続けて"])
def test_a_typed_line_passes_and_opens_no_window(monkeypatch, mode, line):
    monkeypatch.setenv("ZAELAR_ATTENTION", mode)
    from voice.engine.pipeline import agent_events
    monkeypatch.setattr(agent_events, "_route_typed", lambda *a, **k: None)
    ok, events = _typed_turn(line)
    assert ok, "a typed line is directed by itself — the gate must let it through"
    assert not attention.window_open(), "a typed turn opened the voice window: the room's next words become orders"
    directed = [e for e in events if e[0] == "ambient" and (e[2].get("extra") or {}).get("directed")]
    assert not directed, f"a DIRECTED ambient verdict lights the client ring and unparks the tap: {directed}"
    # …and the room right after it is still the room.
    assert attention.evaluate("Finch.").directed is False


def test_a_spoken_line_after_a_typed_one_is_judged_as_speech(monkeypatch):
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")
    from voice.engine.pipeline import agent_events
    monkeypatch.setattr(agent_events, "_route_typed", lambda *a, **k: None)
    _typed_turn("yes.")
    ok, _, _ = asyncio.run(attention_turn.judge("No.", context="", emit=lambda *a, **k: None))
    assert ok is False, "a spoken word after a typed turn rode the typed line's admission"
