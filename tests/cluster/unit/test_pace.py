#
# Tests del CRITERIO de conversación por INTELIGENCIA (V2-075) + señal estructural de repetición.
# Run: .venv/bin/pytest tests/cluster/unit/test_pace.py -q
#
# El juicio de si una conversación fluye/está atascada/no tiene sentido lo hace un MODELO (genérico, no patrones
# hardcodeados que solo se adaptan a UN peer). Aquí probamos: (1) el parseo/validación del veredicto de catálogo
# CERRADO + fail-open, (2) que la petición al modelo marca el contenido como material a evaluar (no instrucciones),
# (3) `evaluate()` con un modelo simulado, (4) la señal estructural `near_repeat` (única heurística determinista).
#
import asyncio

import pytest

from connectors.meshkore import capsule, evaluator


# ── parseo/validación del veredicto (catálogo cerrado + fail-open) ──────────────────────────────────────────────
def test_parse_valid_verdict():
    v = evaluator.parse('{"health":"stuck","action":"hand_back","reason":"se repite"}')
    assert v == {"health": "stuck", "action": "hand_back", "reason": "se repite"}


def test_parse_extracts_json_from_noise():
    v = evaluator.parse('Claro, mi veredicto:\n{"health":"flowing","action":"continue","reason":"ok"} — fin')
    assert v["health"] == "flowing" and v["action"] == "continue"


@pytest.mark.parametrize("bad", [
    "",                                                        # vacío
    "no es json",                                              # sin json
    '{"health":"raro","action":"continue"}',                 # health fuera del catálogo
    '{"health":"stuck","action":"borra_todo"}',              # action fuera del catálogo (no concede acciones)
    '{"foo":1}',                                               # sin campos
])
def test_parse_failopen_to_continue(bad):
    v = evaluator.parse(bad)
    assert v["health"] == "flowing" and v["action"] == "continue"    # ante la duda, no cortar


# ── la petición al modelo: métricas + contenido marcado como NO-instrucciones ──────────────────────────────────
def test_build_messages_marks_content_as_data():
    msgs = evaluator.build_messages(
        [{"who": "peer", "text": "hola"}, {"who": "us", "text": "qué tal"}],
        {"turns": 5, "given": 3000, "received": 500, "ratio": 6.0})
    sys, user = msgs[0]["content"].lower(), msgs[1]["content"]
    assert "no instrucciones" in user.lower() or "material a evaluar" in user.lower()
    assert "PEER:" in user and "NOSOTROS:" in user
    assert "6.0x" in user and "turnos=5" in user
    assert "flowing" in sys and "pause" in sys        # el catálogo cerrado está en el system


# ── evaluate() con un modelo SIMULADO (sin LLM real) ────────────────────────────────────────────────────────────
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
    assert v["action"] == "continue"                  # un fallo de infra NUNCA corta la charla


# ── señal ESTRUCTURAL de repetición (única heurística determinista, genérica) ───────────────────────────────────
def test_near_repeat_detects_reworded():
    recent = ["Estamos en fase Definición aún, no puedo discutir Diseño hasta cerrar la fase actual"]
    assert capsule.near_repeat(
        "Aún estamos en la fase Definición y no puedo discutir el Diseño hasta que cerremos la fase actual", recent)


def test_near_repeat_false_on_new_content():
    recent = ["Estamos en fase Definición, no puedo discutir Diseño"]
    assert not capsule.near_repeat("Los features son returns, ATR y volumen; ¿cerramos la definición?", recent)


def test_no_hardcoded_stuck_matcher():
    # el anti-patrón (regex de frases por-agente) NO debe existir ya: el juicio semántico es del modelo.
    assert not hasattr(capsule, "looks_stuck")
    assert not hasattr(capsule, "advanced")
