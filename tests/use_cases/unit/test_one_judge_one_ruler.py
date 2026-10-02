"""V2-779 F2 — every use case is graded by ONE ruler: Claude Code on the licence, with an exact model id.

The ledger on 2026-10-02 held rows graded by four models (glm-4.6 ×40, deepseek-v4-pro ×21, v4-flash ×5, the
licence ×1) because the judge fell down a chain by quota; their notes are not comparable. Operator's rule, same
day: the judge is Claude Code with the licence, always, and every other option is removed. A judge that cannot
answer makes the round INFRA — it is never graded by someone else.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import llm


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def test_the_judge_is_the_licence_with_the_pinned_id(monkeypatch):
    seen = {}

    def _licence(messages, max_tokens=4000, model=""):
        seen["model"] = model
        return '{"overall": 4}'
    monkeypatch.setattr(llm, "_claude_licence", _licence)
    txt, used = llm.judge_call([{"role": "user", "content": "puntúa"}])
    assert txt == '{"overall": 4}'
    assert seen["model"] == llm.JUDGE_MODEL == "claude-sonnet-5", "an alias moves; the ruler must not"
    assert used == "licencia-claude/claude-sonnet-5", "the ledger records WHICH ruler"


def test_there_is_no_other_rung_to_fall_to():
    """The paid chain is gone from this module, not just skipped: nothing can grade a round with another model."""
    assert not hasattr(llm, "_voice_judge_call")


def test_a_licence_that_cannot_answer_makes_the_round_INFRA_not_another_judge(monkeypatch):
    calls = {"n": 0}

    def _down(*a, **k):
        calls["n"] += 1
        raise RuntimeError("rc=1: rate limited")
    monkeypatch.setattr(llm, "_claude_licence", _down)
    with pytest.raises(RuntimeError, match="juez no disponible"):
        llm.judge_call([{"role": "user", "content": "x"}])
    assert calls["n"] == 2, "one retry, then the round is parked as INFRA by the caller"


def test_an_EMPTY_answer_is_not_a_verdict(monkeypatch):
    monkeypatch.setattr(llm, "_claude_licence", lambda *a, **k: "   ")
    with pytest.raises(RuntimeError, match="VAC"):
        llm.judge_call([{"role": "user", "content": "x"}])


def test_a_transient_failure_is_retried_once(monkeypatch):
    answers = iter([RuntimeError("timeout"), '{"overall": 5}'])

    def _flaky(*a, **k):
        x = next(answers)
        if isinstance(x, Exception):
            raise x
        return x
    monkeypatch.setattr(llm, "_claude_licence", _flaky)
    assert llm.judge_call([{"role": "user", "content": "x"}])[0] == '{"overall": 5}'
