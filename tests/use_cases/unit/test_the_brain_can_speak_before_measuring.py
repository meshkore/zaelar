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


def test_the_refusal_REPEATS_what_the_engine_said(monkeypatch):
    """The response already carried the diagnosis; for eight hours the refusal threw it away.

    A retry loop read «no se puede medir (exit 4)» 46 times and never learned which provider refused or
    why, while every single one of those responses was holding `error: 402 Insufficient Balance` and the
    `spec` of the rung that had been tried.
    """
    monkeypatch.setattr(R.probe_client, "say", lambda *a, **k: {
        "ok": False,
        "error": "modelo: Error code: 402 - {'message': 'Insufficient Balance'}",
        "spec": "deepseek/deepseek-v4-pro"})
    out = R.brain_preflight()
    assert "Insufficient Balance" in out, "the reason must be printed, not looked for"
    assert "deepseek/deepseek-v4-pro" in out, "and WHICH rung refused"


def test_a_silent_refusal_still_refuses(monkeypatch):
    """No `error` field is the older shape and must not become a crash or a pass."""
    monkeypatch.setattr(R.probe_client, "say", lambda *a, **k: {"reply": ""})
    out = R.brain_preflight()
    assert "NO PUEDE HABLAR" in out and "LO QUE DIJO EL MOTOR" not in out
