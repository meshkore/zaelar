"""Every model call carries ONE usage shape (V2-837 G4/G5).

The flash reply said its model, tokens, prompt size, TTFT and finish reason; a decision read (Jev) said none of it
(0 of 90 `jev read` rows had a model or a latency) and a Brain Worker reported one total at the very end (18 of 414
worker rows named a model, 12 had tokens), so «the context is filling up» and «the classifier is slow today» could not
be seen. `observability/usage.py` is the shape; the Jev call and its reads, and every worker TURN, carry it.

Disarm: drop `**_read_usage(v)` from `nucleo/jev._emit_read` → the read case goes red; drop
`**self._turn_usage_once()` from `session_notes._emit_step` → the worker case goes red; drop `_turn_facts` from the
Claude stream mapper → the worker case goes red.
"""
from __future__ import annotations

import pytest

from observability import usage

CORE = {"model", "provider", "ms", "outcome"}


@pytest.fixture
def events(monkeypatch):
    from voice import observer
    got = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: got.append(
        (kind, label, dict(extra or {}))))
    return got


def test_the_shape_has_one_vocabulary():
    with pytest.raises(TypeError):
        usage.shape(model="m", tokens_in=3)                       # a second name is a second shape
    u = usage.shape(model="m", provider="p", prompt_tokens="12", ms=3.4, outcome="ok", finish_reason="")
    assert u == {"model": "m", "provider": "p", "prompt_tokens": 12, "ms": 3, "outcome": "ok"}
    assert usage.FIELDS[0] == "model" and "outcome" in usage.FIELDS


def _stream(sess, objs):
    out = []
    for o in objs:
        out.extend(sess._map(o))
    return out


def test_a_worker_turn_carries_the_shape_once_on_its_first_row(events):
    from nucleo.workers import session as S
    from nucleo.workers.base import WorkerEvent
    from nucleo.workers.providers.claude import ClaudeCodeSession

    cc = object.__new__(ClaudeCodeSession)
    cc._model, cc._task_id, cc._tier = "alias", "9", {"name": "tier-a", "base_url": ""}
    cc._steps_by_id, cc._last_step, cc._ctx_tokens = {}, {}, 0
    use = {"input_tokens": 100, "cache_read_input_tokens": 900, "output_tokens": 20}
    msg = {"id": "m1", "model": "real-1", "usage": use, "stop_reason": "tool_use"}
    evs = _stream(cc, [
        {"type": "system", "subtype": "init", "session_id": "n1", "model": "alias"},
        {"type": "assistant", "message": {**msg, "content": [{"type": "text", "text": "looking"}]}},
        {"type": "assistant", "message": {**msg, "content": [
            {"type": "tool_use", "id": "u1", "name": "WebSearch", "input": {"query": "cars"}}]}},
    ])
    turns = [e for e in evs if e.type == "usage" and e.data.get("turn")]
    assert len(turns) == 1, "the CLI repeats a message's usage per block: one turn, counted once"

    s = S.WorkerSession.__new__(S.WorkerSession)
    s._rec = S.SessionRecord(task_id="9", goal="find a car", kind="web")
    s._usage_partial, s._model, s._base_url, s._ctx_warned = {}, "alias", "", True
    s._first_output_at, s._started_at = 1.0, 0.0
    s._spin, s._spin_dead, s._perm_hits = {}, False, 0
    s._emit_chip = s._touch = s._bus = (lambda *a, **k: None)
    for e in evs:
        if e.type in ("usage", "note", "step"):
            s._on_event(WorkerEvent(task_id="9", type=e.type, data=e.data))
    rows = [(lbl, ex) for _, lbl, ex in events]
    first, rest = rows[0][1], [ex for _, ex in rows[1:]]
    assert CORE - {"ms"} <= set(first) and first["model"] == "real-1" and first["provider"] == "tier-a", first
    assert first["prompt_tokens"] == 1000 and first["completion_tokens"] == 20 and first["cached_tokens"] == 900
    assert first["ctx_tokens"] == 1000 and first["finish_reason"] == "tool_use"
    assert rest and all("outcome" not in ex for ex in rest), "the turn's usage rides on its FIRST row only"

    # a turn with no narration: its first row is the tool step, and the usage rides there
    events.clear()
    m2 = {"id": "m2", "model": "real-1", "usage": use, "stop_reason": "tool_use", "content": [
        {"type": "tool_use", "id": "u2", "name": "WebFetch", "input": {"url": "https://example.org"}}]}
    for e in _stream(cc, [{"type": "assistant", "message": m2}]):
        if e.type in ("usage", "note", "step"):
            s._on_event(WorkerEvent(task_id="9", type=e.type, data=e.data))
    (_, _, step), = events
    assert step.get("outcome") == "ok" and step.get("model") == "real-1", step
