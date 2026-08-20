"""The judge did not know what day it was, and graded dates anyway.

Measured on 2026-08-20 (round 15 of `remember-and-remind-deadline`): the user said "el jueves" on a THURSDAY,
zaelar resolved the NEXT Thursday (27 August) and set the reminder for Wednesday the 26th. That is coherent —
you cannot warn somebody the day before something that is today. The judge filed it as a [high] finding: "the
natural Thursday is the 20th, the reminder lands 6 days late". That finding was on its way to the engine team
as a product defect.

The cause was not the model: the prompt simply did not carry the calendar. A judge with no date cannot evaluate
dates, and tries anyway.
"""
from __future__ import annotations

import datetime

from tests.use_cases.e2e.agent import judge as J


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p",
                              opening_line="apúntame algo para el jueves", success_checks="s")


def _prompt(monkeypatch) -> str:
    """The REAL prompt that reaches the judge, without calling any model: `llm.judge_call` is patched, which is
    its only point of contact with one."""
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "test-model"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), {"transcript": [], "mechanism_report": {}})
    return seen.get("user", "")


def test_the_judge_is_told_todays_date_and_weekday(monkeypatch):
    txt = _prompt(monkeypatch)
    hoy = datetime.date.today()
    assert hoy.isoformat() in txt, "the judge does not know what date it is"
    assert J._DIAS[hoy.weekday()] in txt, "the WEEKDAY is missing, and that is what resolves \"el jueves\""


def test_and_told_that_a_weekday_means_the_NEXT_one(monkeypatch):
    """The concrete rule that would have avoided the false positive: if today is Thursday, "el jueves" is the next one."""
    txt = _prompt(monkeypatch)
    assert "PRÓXIMO" in txt
    assert "la semana siguiente" in txt


def test_and_told_NOT_to_invent_a_finding_when_the_date_fits(monkeypatch):
    """Without this half the notice only changes WHICH date the judge prefers, instead of silencing it when there is no defect."""
    txt = _prompt(monkeypatch)
    assert "solo está MAL si contradice" in txt
    assert "NO es un hallazgo" in txt


def test_the_reminder_rule_is_about_ORDER_not_about_which_day(monkeypatch):
    """The false finding said "lands 6 days late". The only thing that matters is that the reminder comes BEFORE the event."""
    txt = _prompt(monkeypatch)
    assert "va ANTES del evento" in txt


def test_with_search_down_REFUSING_to_answer_scores_HIGH(monkeypatch):
    """The engine team asked this before risking a regression (2026-08-20), and they were right.

    Their `quick-fact-opening-hours` fix makes the turn replace an improvised figure with "I could not check
    it, I would rather not give you a made-up number" when search is down. The case's `success_checks` asks for
    both facts answered, so the judge would have filed it as a result failure — punishing exactly the behaviour
    the case exists to obtain. It is the same principle that already governs credential-capped cases: saying
    what is missing scores, faking is the grave one.
    """
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "test-model"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), {"transcript": [], "mechanism_report": {
        "search_health": {"degraded": True, "reasons": [("captcha", 3)], "n_search_events": 3}}})
    txt = seen["user"]
    assert "se NEGÓ a dar un dato" in txt
    assert "puntúa ALTO" in txt
    assert "describe el caso con el entorno SANO" in txt


def test_but_a_healthy_search_gets_no_such_pass(monkeypatch):
    """Sensitivity: with search HEALTHY, refusing to answer IS a result failure and the notice must not appear —
    if it always did, the harness would forgive an agent that never searches."""
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "m"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), {"transcript": [], "mechanism_report": {
        "search_health": {"degraded": False, "n_search_events": 4}}})
    assert "se NEGÓ a dar un dato" not in seen["user"]
