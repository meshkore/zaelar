"""A Brain Worker's model call is ONE observer row, with what it was handed and what it answered (capture gaps,
2026-11-06).

The usage of a worker turn rode on the turn's first step or narration, and the call itself had no row: what the model
was HANDED (the tool results, or the brief) and what it ANSWERED had to be rebuilt from the rows around it. Now the
Claude stream mapper opens a call on the first block of an assistant message and closes it on the next answer, the
next message or the result, and the session writes ONE `model_call` row: the usage shape, `input` and the output as
text — both bounded and scrubbed.

Disarm: close nothing on a `user`/`result` in `claude_calls._map_with_calls` → red; drop `scrub(` from
`session_events._emit_model_call` → the token case goes red.
"""
from __future__ import annotations

import pytest

from nucleo.workers import session as S
from nucleo.workers.base import WorkerEvent
from nucleo.workers.providers.claude import ClaudeCodeSession   # the facade first: it binds claude_map
from nucleo.workers.providers import claude_calls as claude_map  # noqa: E402 — CALL_OUT_MAX lives there


@pytest.fixture
def rows(monkeypatch):
    out: list[tuple[str, str, str, dict]] = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None: out.append(
        (kind, label, text, dict(extra or {}))))
    return out


def _mapper():
    cc = object.__new__(ClaudeCodeSession)
    cc._model, cc._task_id, cc._tier = "alias", "7", {"name": "tier-a", "base_url": ""}
    cc._steps_by_id, cc._last_step, cc._ctx_tokens = {}, {}, 0
    return cc


def _session():
    s = S.WorkerSession.__new__(S.WorkerSession)
    s._rec = S.SessionRecord(task_id="7", goal="find a used car under 9000 EUR", kind="web")
    s._usage_partial, s._model, s._base_url, s._ctx_warned = {}, "alias", "", True
    s._first_output_at, s._started_at = 1.0, 0.0
    s._spin, s._spin_dead, s._perm_hits = {}, False, 0
    s._emit_chip = s._touch = s._bus = (lambda *a, **k: None)
    return s


def _run(objs):
    cc, s = _mapper(), _session()
    evs = []
    for o in objs:
        evs.extend(cc._map(o))
    for e in evs:
        if e.type in ("usage", "note", "step", "model_call"):
            s._on_event(WorkerEvent(task_id="7", type=e.type, data=e.data))
    return evs


USE = {"input_tokens": 50, "output_tokens": 12}


def _assistant(mid, *content):
    return {"type": "assistant", "message": {"id": mid, "model": "real-1", "usage": USE, "stop_reason": "tool_use",
                                             "content": list(content)}}


def test_each_call_is_one_row_with_its_input_and_its_output(rows):
    evs = _run([
        {"type": "system", "subtype": "init", "session_id": "n1", "model": "alias"},
        _assistant("m1", {"type": "text", "text": "I will search the listings first"}),
        _assistant("m1", {"type": "tool_use", "id": "u1", "name": "WebSearch", "input": {"query": "used cars"}}),
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "u1",
                                                   "content": "Seat Ibiza 2019 8500 EUR"}]}},
        _assistant("m2", {"type": "text", "text": "The Ibiza fits the budget"}),
        {"type": "result", "subtype": "success", "result": "done", "usage": USE},
    ])
    assert [e.type for e in evs].count("model_call") == 2
    calls = [r for r in rows if r[0] == "model_call"]
    assert [c[3]["n"] for c in calls] == [1, 2]
    first, second = calls
    assert first[1] == "🧠 real-1" and first[3]["input"].startswith("brief: find a used car"), first
    assert "I will search the listings first" in first[2] and "WebSearch" in first[2]
    assert first[3]["tools"] == ["WebSearch"] and first[3]["completion_tokens"] == 12 and first[3]["model"] == "real-1"
    assert "Seat Ibiza 2019" in second[3]["input"] and "The Ibiza fits" in second[2]


def test_the_summaries_are_bounded_and_scrubbed(rows):
    secret = "sk-" + "ant-" + "api03-" + "A" * 60      # built at run time: no key-shaped literal in the source
    _run([
        _assistant("m1", {"type": "text", "text": f"key {secret} " + "word " * 400}),
        {"type": "user", "message": {"content": []}},
    ])
    (call,) = [r for r in rows if r[0] == "model_call"]
    assert len(call[2]) <= claude_map.CALL_OUT_MAX
    assert secret not in call[2], "a token-shaped value never reaches the record"


def test_a_message_the_cli_made_is_not_a_model_call(rows):
    evs = _run([
        {"type": "assistant", "message": {"id": "s1", "model": "<synthetic>", "content": [{"type": "text", "text": "x"}]}},
        {"type": "result", "subtype": "success", "result": "done"},
    ])
    assert "model_call" not in [e.type for e in evs]


def test_a_record_that_fails_never_breaks_the_worker(monkeypatch):
    import voice.observer as obs

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(obs, "emit", boom)
    _run([_assistant("m1", {"type": "text", "text": "hi"}), {"type": "user", "message": {"content": []}}])
