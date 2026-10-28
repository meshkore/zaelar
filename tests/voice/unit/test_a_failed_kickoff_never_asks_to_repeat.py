"""A failed kickoff never asks the operator to repeat himself (V2-789).

The first turn of a session is the agent's greeting: it answers nothing the operator said. When the model behind it
failed — a provider 503, a stall, a fault of ours — the turn fell to the reply-shaped «say that again?», asking him to
repeat words he never spoke. The fallback line is now chosen by what the turn IS: the kickoff gets the i18n
`kickoff_fallback`, a reply keeps `say_again`. Every variant below crosses failure cause × language × turn shape.

Disarm: make `turn_failure._fallback_line` ignore `first_turn` (always `say_again`) → red.
"""
from __future__ import annotations

import asyncio

import pytest

from i18n import langs


def _run(*, first_turn, stalled=False, err_exc=None, err_text=""):
    from voice.engine.llm.providers import turn_failure
    sent = []
    out = asyncio.run(turn_failure.say_the_turn_failed(
        emit=lambda *a, **k: None, err_exc=err_exc, err_text=err_text, errored=True, llm_metrics={},
        send=sent.append, spec=None, stalled=stalled, first_turn=first_turn))
    assert out == {"__return__": True}
    return sent


@pytest.fixture
def _no_ladder(monkeypatch):
    """The provider verdict is not under test: an outage with a stand-in still available (not dry)."""
    from nucleo.llm import provider_failure
    monkeypatch.setattr(provider_failure, "handle", lambda *a, **k: {"relay": None, "dry": False})


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_stalled_kickoff_greets_instead_of_asking_to_repeat(monkeypatch, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    sent = _run(first_turn=True, stalled=True)
    assert sent == [langs.spec(code).kickoff_fallback], sent
    assert langs.spec(code).say_again not in sent


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_kickoff_whose_provider_is_down_greets(monkeypatch, _no_ladder, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    sent = _run(first_turn=True, err_text="Error code: 503 - provider_unavailable", err_exc=RuntimeError("503"))
    assert sent == [langs.spec(code).kickoff_fallback], sent


def test_a_kickoff_that_hit_an_engine_fault_greets(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    sent = _run(first_turn=True, err_exc=UnboundLocalError("x"), err_text="x")
    assert sent == [langs.spec("en").kickoff_fallback], sent


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_reply_turn_still_asks_again(monkeypatch, _no_ladder, code):
    monkeypatch.setenv("ZAELAR_LANGUAGE", code)
    assert _run(first_turn=False, err_text="Error code: 503", err_exc=RuntimeError("503")) == \
        [langs.spec(code).say_again]
    assert _run(first_turn=False, stalled=True) == [langs.spec(code).say_again]


def test_an_engine_fault_on_a_reply_speaks_the_session_language(monkeypatch):
    """The engine-fault branch carried its own hard-coded Spanish sentence; it now shares the one chooser."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    assert _run(first_turn=False, err_exc=UnboundLocalError("x"), err_text="x") == [langs.spec("en").say_again]


def test_both_shipped_languages_carry_a_kickoff_fallback():
    for code in ("es", "en"):
        line = langs.spec(code).kickoff_fallback
        assert line and line != langs.spec(code).say_again, (code, line)


def test_the_voice_turn_tells_the_failure_path_what_the_turn_is():
    """WIRING: the chooser is only as good as its input — the voice turn must hand it `first_turn`."""
    import pathlib
    import re
    src = (pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text()
    call = re.search(r"_turn_failure\.say_the_turn_failed\((.*?)\n\s*\)", src, re.S)
    assert call and "first_turn=first_turn" in call.group(1), "the failed-turn call does not pass first_turn"
