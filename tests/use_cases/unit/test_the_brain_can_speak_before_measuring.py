"""One throwaway turn before the batch, because two rounds were spent learning the chain was dead.

On 2026-08-21 DeepSeek answered HTTP 402 'Insufficient Balance' and the log said 'SIN RELEVO disponible';
every zaelar turn came back empty. The first round was filed 1/1/1/1/1 FAIL on a case nobody exercised;
the second was a case that had PASSED twice an hour earlier.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import run as R


def test_a_talking_brain_passes(monkeypatch):
    monkeypatch.setattr(R.probe_client, "say", lambda *a, **k: {"reply": "ok"})
    assert R.brain_preflight() == ""


def test_an_EMPTY_reply_refuses_and_names_the_usual_cause(monkeypatch):
    monkeypatch.setattr(R.probe_client, "say", lambda *a, **k: {"reply": ""})
    out = R.brain_preflight()
    assert "NO PUEDE HABLAR" in out
    assert "SIN RELEVO" in out, "the refusal must say where to look"


def test_whitespace_is_not_an_answer(monkeypatch):
    """The mute turns came back as empty strings and as lone newlines; both are silence."""
    monkeypatch.setattr(R.probe_client, "say", lambda *a, **k: {"reply": "   \n  "})
    assert R.brain_preflight() != ""


def test_an_unreachable_engine_says_THAT_instead(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("no route")
    monkeypatch.setattr(R.probe_client, "say", boom)
    out = R.brain_preflight()
    assert "no contesta" in out and "no se ha medido nada" in out


def test_the_preflight_turn_never_touches_memory(monkeypatch):
    """It must not write a test conversation into the round's own memory: the case under measurement is
    entitled to a clean one."""
    seen = {}
    monkeypatch.setattr(R.probe_client, "say", lambda *a, **k: seen.update(k) or {"reply": "ok"})
    R.brain_preflight()
    assert seen.get("ingest") is False
    assert seen.get("execute") is False, "a preflight must not fire tools"
