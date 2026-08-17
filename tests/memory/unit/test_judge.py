"""Tests de tests/memory/judge/judge.py (V2-105) — mecánica del parseo/schema, con chat_sync mockeado.

El juez en sí (juicio REAL contra DeepSeek) se valida con coste real en
`tests/memory/judge/calibrate.py`, no aquí — mismo patrón que V2-104's `live_rem_faithfulness.py` vs
`test_rem.py`: mocks para la mecánica en cada commit, script aparte para el juicio real con coste.
"""
from nucleo import memllm
from tests.memory.judge import judge as J


def test_judge_recall_parses_valid_verdict(monkeypatch):
    monkeypatch.setattr(memllm, "chat_sync",
                        lambda *a, **k: '{"veredicto": "correct", "razon": "coincide", "cita": "texto"}')
    v = J.judge_recall("¿pregunta?", "algo recuperado", "hecho vigente")
    assert v["veredicto"] == "correct"
    assert v["razon"] == "coincide"


def test_judge_recall_rejects_verdict_outside_catalog(monkeypatch):
    monkeypatch.setattr(memllm, "chat_sync", lambda *a, **k: '{"veredicto": "quizas", "razon": "no sé"}')
    v = J.judge_recall("¿pregunta?", "algo", "hecho")
    assert v["veredicto"] == "absent"
    assert v["_error"] == "unparseable"


def test_judge_recall_fail_open_on_no_response(monkeypatch):
    monkeypatch.setattr(memllm, "chat_sync", lambda *a, **k: None)
    v = J.judge_recall("¿pregunta?", "algo", "hecho")
    assert v["veredicto"] == "absent"
    assert v["_error"] == "no_content"


def test_judge_recall_fail_open_on_garbage_response(monkeypatch):
    monkeypatch.setattr(memllm, "chat_sync", lambda *a, **k: "esto no es JSON en absoluto")
    v = J.judge_recall("¿pregunta?", "algo", "hecho")
    assert v["veredicto"] == "absent"
    assert v["_error"] == "unparseable"


def test_judge_recall_all_catalog_verdicts_accepted(monkeypatch):
    for verdict in J.VERDICTS:
        monkeypatch.setattr(memllm, "chat_sync",
                            lambda *a, _v=verdict, **k: f'{{"veredicto": "{_v}", "razon": "x"}}')
        v = J.judge_recall("¿?", "r", "g")
        assert v["veredicto"] == verdict
