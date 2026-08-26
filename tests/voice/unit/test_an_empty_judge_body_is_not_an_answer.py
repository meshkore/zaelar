"""V2-338 — un 200 con cuerpo VACÍO no es una respuesta del juez, en NINGUNA pata.

La regla existía desde el 2026-08-20… solo en la pata de DeepSeek, con su porqué escrito al lado («la cadena
existía y nunca avanzó, porque nada había lanzado»). La pata de GLM no la tenía.

MEDIDO el 2026-08-26 (ronda enfocada de `search-buy-used-car`): GLM contestó 200 con contenido vacío,
`judge_call` lo DEVOLVIÓ como respuesta —el relevo solo salta con excepción—, el juez parseó '' tres veces y
la ronda entera murió como INFRA. Ocho minutos de conversación ya medidos, tirados por la pata que «funcionó».

Verificado en vivo tras el arreglo: GLM vacío → «respuesta VACÍA (200 sin contenido)» → relevo → DeepSeek
devuelve el JSON.
"""
from unittest import mock

import pytest

from tests.voice.e2e.agent import config as C
from tests.voice.e2e.agent import llm


@pytest.fixture
def zai_on(monkeypatch):
    monkeypatch.setattr(C, "JUDGE_PROVIDER", "zai", raising=False)
    monkeypatch.setattr(C, "ZAI_KEY", "k", raising=False)
    monkeypatch.setattr(C, "DEEPSEEK_KEY", "k", raising=False)


def test_glm_vacio_RELEVA_en_vez_de_devolver_nada(zai_on, monkeypatch):
    monkeypatch.setattr(llm, "glm_call", lambda *a, **k: "")
    monkeypatch.setattr(llm, "deepseek_direct_call", lambda *a, **k: '{"ok": true}')
    raw, used = llm.judge_call([{"role": "user", "content": "x"}])
    assert raw == '{"ok": true}'
    assert used == C.DEEPSEEK_JUDGE_MODEL, "el relevo no llegó a DeepSeek"


def test_glm_con_contenido_NO_releva(zai_on, monkeypatch):
    """La sensibilidad: el relevo no puede volverse el camino normal."""
    monkeypatch.setattr(llm, "glm_call", lambda *a, **k: '{"v": 1}')
    def _no(*a, **k): raise AssertionError("no debía llegar a DeepSeek")
    monkeypatch.setattr(llm, "deepseek_direct_call", _no)
    raw, used = llm.judge_call([{"role": "user", "content": "x"}])
    assert raw == '{"v": 1}' and used == C.ZAI_JUDGE_MODEL


def test_solo_espacios_TAMBIEN_es_vacio(zai_on, monkeypatch):
    monkeypatch.setattr(llm, "glm_call", lambda *a, **k: "   \n  ")
    monkeypatch.setattr(llm, "deepseek_direct_call", lambda *a, **k: '{"ok": true}')
    raw, _ = llm.judge_call([{"role": "user", "content": "x"}])
    assert raw == '{"ok": true}'
