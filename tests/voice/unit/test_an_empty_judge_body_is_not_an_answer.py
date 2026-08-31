"""V2-338 — a 200 with an EMPTY body is not a judge response on EITHER path.

The rule had existed since 2026-08-20… but only on the DeepSeek path, with its rationale written beside it
(“the chain existed and never advanced because nothing had launched”). The GLM path did not have it.

MEASURED on 2026-08-26 (focused `search-buy-used-car` run): GLM returned 200 with empty content,
`judge_call` RETURNED it as a response —handoff only triggers on an exception—, the judge parsed '' three times,
and the entire run died as INFRA. Eight minutes of conversation already measured, wasted by the path that
“worked”.

Verified live after the fix: empty GLM → “EMPTY response (200 with no content)” → handoff → DeepSeek
returns the JSON.
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
    """The sensitivity check: handoff must not become the normal path."""
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
