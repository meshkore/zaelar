"""V2-776 D2 — a Brain Worker MUST report where it is; the pulse asks it to when it goes quiet.

The operator (2026-09-27): «hay que hacer trabajar los brain workers obligándoles a actualizar un estado». The
prompt already asked them to report and nothing enforced it: in session 3a9a082c the durable state of a worker
was whatever the observer could infer from its tool calls. Here the pulse demands the report through the
worker's own inbox (`inject`, served piggyback on its next bridge call and on stdin), again and again while it
stays silent — and never for a backend that cannot run the report command.
"""
from __future__ import annotations

import asyncio
import time

from nucleo import dispatch
from nucleo import loop as L
from nucleo.workers.session import SessionRecord


class _Inbox:
    def __init__(self):
        self.said: list[str] = []

    async def inject(self, text):
        self.said.append(text)


def _live(monkeypatch, *, backend="claude_code", reported_s_ago=None, paused=False):
    rec = SessionRecord(task_id="7", goal="búscame piso en Gràcia", status="running", backend=backend)
    rec.started = time.time() - 120                   # past the report window, far from any budget
    rec.last_event_at = time.time()                    # alive: the stream keeps moving
    rec.reported_at = time.time() - reported_s_ago if reported_s_ago is not None else 0.0
    rec.paused = paused
    rec.session = _Inbox()
    monkeypatch.setattr(dispatch, "_SESSIONS", {"7": rec})
    return rec


async def _noop(*a, **k):
    return None


def _pulse(loop, at):
    asyncio.run(loop._supervise_workers(at))


def test_a_worker_that_never_reported_is_told_to(monkeypatch):
    rec = _live(monkeypatch)
    _pulse(L.OrchestratorLoop(deliver=_noop), time.time())
    assert rec.session.said == [L.REPORT_DEMAND]
    assert "agent_report phase" in L.REPORT_DEMAND, "the demand must name the command the worker actually has"


def test_it_is_asked_again_only_after_another_window(monkeypatch):
    rec = _live(monkeypatch)
    loop = L.OrchestratorLoop(deliver=_noop)
    t0 = time.time()
    _pulse(loop, t0)
    _pulse(loop, t0 + 5)                               # the 1 Hz pulse must not repeat it every second
    assert len(rec.session.said) == 1
    _pulse(loop, t0 + L._REPORT_SECS + 1)
    assert len(rec.session.said) == 2


def test_a_worker_that_reported_recently_is_left_alone(monkeypatch):
    rec = _live(monkeypatch, reported_s_ago=10)
    _pulse(L.OrchestratorLoop(deliver=_noop), time.time())
    assert rec.session.said == []


def test_the_widget_generator_and_a_frozen_worker_are_not_asked(monkeypatch):
    """The generator is a one-shot CLI that cannot report; a worker the ⏻ froze cannot read anything."""
    rec = _live(monkeypatch, backend="widget_generator")
    _pulse(L.OrchestratorLoop(deliver=_noop), time.time())
    assert rec.session.said == []
    rec = _live(monkeypatch, paused=True)
    _pulse(L.OrchestratorLoop(deliver=_noop), time.time())
    assert rec.session.said == []


def test_the_worker_prompt_announces_the_obligation():
    """A demand the worker was never told about reads as an interruption; the prompt says it is the rule."""
    from nucleo import dispatch_prompts
    import inspect
    assert "OBLIGATORIO" in inspect.getsource(dispatch_prompts)
