#
# Tests for the conversation-by-INTELLIGENCE CRITERION (V2-075) + structural repetition signal.
# Run: .venv/bin/pytest tests/cluster/unit/test_pace.py -q
#
# A MODEL makes the judgment of whether a conversation is flowing/stuck/meaningless (generic, not hardcoded
# patterns that only adapt to ONE peer). Here we test: (1) parsing/validation of the CLOSED-catalog verdict
# + fail-open, (2) that the request to the model marks the content as material to evaluate (not instructions),
# (3) `evaluate()` with a simulated model, (4) the structural `near_repeat` signal (the only deterministic heuristic).
#
import asyncio

import pytest

from connectors.meshkore import capsule, evaluator


# ── verdict parsing/validation (closed catalog + fail-open) ────────────────────────────────────────────────────
def test_parse_valid_verdict():
    v = evaluator.parse('{"health":"stuck","action":"hand_back","reason":"se repite"}')
    assert v == {"health": "stuck", "action": "hand_back", "reason": "se repite"}


def test_parse_extracts_json_from_noise():
    v = evaluator.parse('Claro, mi veredicto:\n{"health":"flowing","action":"continue","reason":"ok"} — fin')
    assert v["health"] == "flowing" and v["action"] == "continue"


@pytest.mark.parametrize("bad", [
    "",                                                        # empty
    "no es json",                                              # no JSON
    '{"health":"raro","action":"continue"}',                 # health outside the catalog
    '{"health":"stuck","action":"borra_todo"}',              # action outside the catalog (does not grant actions)
    '{"foo":1}',                                               # no fields
])
def test_parse_failopen_to_continue(bad):
    v = evaluator.parse(bad)
    assert v["health"] == "flowing" and v["action"] == "continue"    # when in doubt, do not cut off


# ── request to the model: metrics + content marked as NOT instructions ────────────────────────────────────────
def test_build_messages_marks_content_as_data():
    msgs = evaluator.build_messages(
        [{"who": "peer", "text": "hola"}, {"who": "us", "text": "qué tal"}],
        {"turns": 5, "given": 3000, "received": 500, "ratio": 6.0})
    sys, user = msgs[0]["content"].lower(), msgs[1]["content"]
    assert "no instrucciones" in user.lower() or "material a evaluar" in user.lower()
    assert "PEER:" in user and "NOSOTROS:" in user
    assert "6.0x" in user and "turnos=5" in user
    assert "flowing" in sys and "pause" in sys        # the closed catalog is in the system


# ── evaluate() with a SIMULATED model (without a real LLM) ────────────────────────────────────────────────────
class _FakeFC:
    def __init__(self, out): self._out = out
    async def complete(self, messages, *, spec, max_tokens=200): return self._out


def test_evaluate_returns_model_verdict(monkeypatch):
    import nucleo.flash.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", lambda: _FakeFC('{"health":"dead_end","action":"pause","reason":"bloqueado"}'))
    v = asyncio.run(evaluator.evaluate([{"who": "peer", "text": "x"}] * 4, {"turns": 9}, spec=object()))
    assert v["action"] == "pause" and v["health"] == "dead_end"


def test_evaluate_failopen_on_model_error(monkeypatch):
    class _Boom:
        async def complete(self, *a, **k): raise RuntimeError("modelo caído")
    import nucleo.flash.fast_client as fc
    monkeypatch.setattr(fc, "FastClient", lambda: _Boom())
    v = asyncio.run(evaluator.evaluate([{"who": "peer", "text": "x"}] * 4, {}, spec=object()))
    assert v["action"] == "continue"                  # an infrastructure failure NEVER cuts off the conversation


# ── STRUCTURAL repetition signal (only deterministic, generic heuristic) ──────────────────────────────────────
def test_near_repeat_detects_reworded():
    recent = ["Estamos en fase Definición aún, no puedo discutir Diseño hasta cerrar la fase actual"]
    assert capsule.near_repeat(
        "Aún estamos en la fase Definición y no puedo discutir el Diseño hasta que cerremos la fase actual", recent)


def test_near_repeat_false_on_new_content():
    recent = ["Estamos en fase Definición, no puedo discutir Diseño"]
    assert not capsule.near_repeat("Los features son returns, ATR y volumen; ¿cerramos la definición?", recent)


def test_no_hardcoded_stuck_matcher():
    # The anti-pattern (per-agent phrase regex) must NO longer exist: semantic judgment belongs to the model.
    assert not hasattr(capsule, "looks_stuck")
    assert not hasattr(capsule, "advanced")
