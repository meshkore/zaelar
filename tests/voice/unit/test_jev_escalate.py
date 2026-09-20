"""Node 3.62 — Jev second opinion on a would-be worker commission (T-jev-escalate).

Contract under test (`nucleo/flash/escalation_guard.py`): `judge_escalation` answers
"handle_inline" ONLY on a confident Jev verdict over {handle_inline, escalate}, read from the
operator's words plus state facts (goals in flight, workers active, a worker waiting) — never
a new word list. Every other outcome — confident `escalate`, unsure, unknown, slow, failed,
disabled, empty — returns "escalate", i.e. today's path untouched. The gate only ever clears
a surviving commission; it never commissions one.
"""
from __future__ import annotations

import pytest

from nucleo import jev
from nucleo.flash import escalation_guard as _eg


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV_TIMEOUT_MS", "900")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)
    monkeypatch.setattr(jev, "_read_key", lambda: "k")
    monkeypatch.setattr("voice.observer.emit", lambda *a, **k: None)
    yield


def _canned(choice="handle_inline", confidence=0.9):
    return {"model": "jev-latest",
            "answers": {"escalate_or_inline": {"type": "choice", "choice": choice,
                                               "probabilities": {choice: confidence},
                                               "confidence": confidence}}}


def test_the_question_is_two_answers_over_the_operators_words_plus_state(monkeypatch):
    """The catalog is fixed and reviewable; the state facts travel as context, not as rails."""
    seen: dict = {}
    # NOTE: _post_question takes (answer_key, state, instructions, criteria, timeout) — the
    # state facts ride inside `state` (choose_sync appends context there). Read them back.
    monkeypatch.setattr(jev, "_post_question",
                        lambda ak, st, ins, crit, to: (seen.update(
                            answer_key=ak, criteria=crit, state=st), _canned())[1])
    out = _eg.judge_escalation("It is", running_goals=["find a plumber"],
                               has_workers=True, ask_pending=True)
    assert out == "handle_inline"
    assert seen["answer_key"] == "escalate_or_inline"
    assert set(seen["criteria"]) == {"handle_inline", "escalate"}
    assert "It is" in seen["state"]
    assert "find a plumber" in seen["state"]
    assert "Workers active now: yes" in seen["state"]
    assert "waiting for the operator's answer: yes" in seen["state"]


def test_a_confident_escalate_changes_nothing(monkeypatch):
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="escalate"))
    assert _eg.judge_escalation("research roman culture for me") == "escalate"


def test_unsure_or_unknown_keep_todays_path(monkeypatch):
    """The load-bearing guard: a shrug must not annul a commission. Removing the gate turns
    these red."""
    monkeypatch.setattr(jev, "_post_question",
                        lambda *a: _canned(choice="handle_inline", confidence=0.2))
    assert _eg.judge_escalation("It is") == "escalate"
    monkeypatch.setattr(jev, "_post_question", lambda *a: _canned(choice="teleport"))
    assert _eg.judge_escalation("It is") == "escalate"


def test_failed_disabled_and_empty_never_annul(monkeypatch):
    def _boom(*a):
        raise TimeoutError("slow")
    monkeypatch.setattr(jev, "_post_question", _boom)
    assert _eg.judge_escalation("It is") == "escalate"

    calls: list = []
    monkeypatch.setattr(jev, "_post_question", lambda *a: (calls.append(a), _canned())[1])
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert _eg.judge_escalation("It is") == "escalate"
    monkeypatch.delenv("ZAELAR_JEV")
    assert _eg.judge_escalation("   ") == "escalate"
    assert calls == []
