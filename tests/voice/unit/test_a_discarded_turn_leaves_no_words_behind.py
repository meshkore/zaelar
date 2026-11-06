"""A turn the gate discarded leaves no words behind in the speech engine (2026-11-06).

Measured on his engine: «So now open, uh, the messages.» was judged ambient and dropped; the tap parked before the
end of turn, so the speech engine never committed that line and kept it in its transcript buffer. When audio reopened
on the agent's own question, 0.55 s of room noise closed a turn that carried the stale line, byte-identical, as a NEW
turn 15 s later — behind the question, as if he had just said it.

The gate consumed those words, so the buffer must forget them: the session installs its «clear the uncommitted user
turn» beside the input door (`open_mic_door`), and the one function every early exit of the gate calls
(`_release_acc_trace_if_fresh`) asks `mic_input.discard_pending_turn()`.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from voice import mic_input

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean():
    mic_input.use_turn_clearer(None)
    yield
    mic_input.use_turn_clearer(None)


def test_the_installed_clearer_runs_once_per_discard_and_only_ours_is_removed():
    calls = []
    mic_input.use_turn_clearer(lambda: calls.append(1))
    assert mic_input.discard_pending_turn() is True and calls == [1]
    other = lambda: calls.append(2)  # noqa: E731
    mic_input.clear_turn_clearer(other)                 # not ours: the installed one stays
    assert mic_input.discard_pending_turn() is True and calls == [1, 1]
    mic_input.clear_turn_clearer(mic_input._clearer["fn"])
    assert mic_input.discard_pending_turn() is False and calls == [1, 1]


def test_a_clearer_that_raises_never_stops_the_gate():
    def _boom():
        raise RuntimeError("no session")
    mic_input.use_turn_clearer(_boom)
    assert mic_input.discard_pending_turn() is False


def test_every_early_exit_of_the_gate_discards_the_pending_turn(monkeypatch):
    from voice.engine.llm.providers import flow_lifecycle
    seen = []
    monkeypatch.setattr(mic_input, "discard_pending_turn", lambda: seen.append(1) or True)
    brain = SimpleNamespace(_acc=None, _acc_trace_id="t-1")
    flow_lifecycle._release_acc_trace_if_fresh(brain)
    assert seen == [1] and brain._acc_trace_id == ""
    brain = SimpleNamespace(_acc=SimpleNamespace(pending=lambda: True), _acc_trace_id="t-2")
    flow_lifecycle._release_acc_trace_if_fresh(brain)
    assert seen == [1, 1] and brain._acc_trace_id == "t-2", "the buffer is cleared even when a chain is pending"
    # every early exit of the gate goes through that one function (the three measured branches and the rest)
    src = (ROOT / "nucleo/turn/pipeline_gate.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and getattr(n.func, "attr", "") == "_release_acc_trace_if_fresh"]
    assert len(calls) >= 5, "the gate's early exits release through the one function"


def test_the_session_installs_the_clearer_beside_the_input_door():
    from voice.engine.pipeline import agent_events
    cleared, closers = [], []
    session = SimpleNamespace(input=SimpleNamespace(set_audio_enabled=lambda v: None),
                              clear_user_turn=lambda: cleared.append(1),
                              on=lambda name, fn: closers.append(fn))
    agent_events.open_mic_door(session=session)
    assert mic_input.discard_pending_turn() is True and cleared == [1]
    for fn in closers:
        fn()
    assert mic_input.discard_pending_turn() is False, "uninstalled on close"
