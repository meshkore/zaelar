"""A 200 with an empty body is not an answer, and treating it as one loses the round.

Fourth INFRA on `book-hotel-night-known__es`, 2026-08-20, and the first three had a different cause each time
(429, 504, 504 with the retry firing). This one: the direct DeepSeek leg answered 200 with EMPTY content — a
reasoning model can spend its whole output budget thinking — the judge saw no JSON, re-prompted itself three
times against the same silent leg, and gave up. The chain existed and never advanced, because nothing raised.

Two fixes, and the second is the one that saves the conversation: an empty body raises so the chain moves to the
next provider, and a judge that gives up raises instead of returning a hollow verdict. Returning one made the
round look judged-and-empty, so the runner never parked it and eight minutes of driving went in the bin.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import judge as J
from tests.voice.e2e.agent import llm as L


@pytest.fixture(autouse=True)
def _chain(monkeypatch):
    monkeypatch.setattr(L.config, "JUDGE_PROVIDER", "deepseek", raising=False)
    monkeypatch.setattr(L.config, "ZAI_KEY", "", raising=False)
    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "k", raising=False)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def test_an_empty_vendor_answer_falls_through_to_the_broker(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: order.append("vendor") or "   ")
    monkeypatch.setattr(L, "call", lambda *a, **k: order.append("broker") or '{"ok":true}')
    txt, model = L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["vendor", "broker"], "una respuesta vacía dejó la cadena parada"
    assert txt == '{"ok":true}'


def test_an_empty_broker_answer_is_retried_not_returned(monkeypatch):
    calls = {"n": 0}

    def _call(*a, **k):
        calls["n"] += 1
        return "" if calls["n"] == 1 else "{}"

    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "", raising=False)
    monkeypatch.setattr(L, "call", _call)
    L.judge_call([{"role": "user", "content": "x"}])
    assert calls["n"] == 2, "devolver el vacío haría que el juez se pelease con su propio prompt"


def test_a_real_answer_is_never_touched(monkeypatch):
    """Sensitivity: the guard must not reject a terse but valid verdict."""
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: '{"overall":4}')
    monkeypatch.setattr(L, "call", lambda *a, **k: pytest.fail("no debería llegar al broker"))
    txt, _ = L.judge_call([{"role": "user", "content": "x"}])
    assert txt == '{"overall":4}'


def test_a_judge_that_gives_up_RAISES_so_the_round_gets_parked(monkeypatch):
    """The half that saves the conversation: a hollow verdict looks measured, an exception gets the run parked."""
    monkeypatch.setattr(J.llm, "judge_call", lambda msgs, **k: ("no soy json", "modelo"))
    from tests.use_cases.e2e.agent import scenarios as SC
    scn = SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p", opening_line="o",
                             success_checks="s")
    with pytest.raises(RuntimeError, match="no devolvió JSON"):
        J.judge(scn, {"transcript": [], "mechanism_report": {}})


def test_and_a_judge_that_recovers_on_a_retry_still_works(monkeypatch):
    """Sensitivity for the same change: the self-correction loop must survive, it earns its keep."""
    said = iter(["no soy json", '{"scores":{},"overall":4,"veredicto":"ok"}'])
    monkeypatch.setattr(J.llm, "judge_call", lambda msgs, **k: (next(said), "modelo"))
    from tests.use_cases.e2e.agent import scenarios as SC
    scn = SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p", opening_line="o",
                             success_checks="s")
    v = J.judge(scn, {"transcript": [], "mechanism_report": {}})
    assert v["overall"] == 4 and v.get("_judge_retries") == 1
