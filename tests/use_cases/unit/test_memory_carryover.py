"""A batch shares ONE engine, so from the third case onward zaelar remembers the earlier ones—and that is NOT
a product defect.

Measured on 2026-08-20: `renew-gym-membership__es` dropped to 2/5 with the verdict “memory relevance failures,
mixing domains (Netflix/Theater) when asking about the gym.” Netflix and Theater are EXACTLY the two cases
that ran before it in the same batch. A fresh installation cannot do that: the finding concerned our setup,
not the agent.

It cannot be fixed by deleting the memory between cases: that requires killing the process (SQLite is in use), and
`/api/reset/full` relaunches the engine—in a sandbox that is worse than the problem. So the fact is STAMPED into
the evidence and reaches the judge before it reasons, just like `search_health`. And with the boundary stated:
remembering another topic is not a failure, but CONFUSING the topic is.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import judge as J


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x", locale="es", tier=2, persona_brief="p",
                              opening_line="o", success_checks="s")


def _prompt(run: dict, monkeypatch) -> str:
    """The REAL prompt received by the judge, captured WITHOUT calling any model.

    `llm.judge_call` is patched; it is the only point through which the judge talks to a model (`judge.py:246`).
    The first version of this helper GUESSED the function name and got it wrong, so it returned "" and
    on top of that made the real call: 12 seconds and an actual cost for a unit test.
    """
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "modelo-de-prueba"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), run)
    return seen.get("user", "")


def test_the_judge_is_told_which_cases_ran_before_this_one(monkeypatch):
    txt = _prompt({"transcript": [], "mechanism_report": {},
                   "memory_carryover": ["cancel-subscription-before-charge__es", "find-theatre-tickets__es"]},
                   monkeypatch)
    assert "MEMORIA COMPARTIDA" in txt
    assert "cancel-subscription-before-charge__es" in txt and "find-theatre-tickets__es" in txt
    assert "NO lo penalices" in txt


def test_and_told_what_WOULD_still_be_a_real_failure(monkeypatch):
    """The half that prevents this from being an amnesty: remembering another topic is not a failure, but confusing the topic is.
    Without this sentence, the notice would teach the judge to forgive exactly the failure the case is looking for."""
    txt = _prompt({"transcript": [], "mechanism_report": {}, "memory_carryover": ["otro-caso"]}, monkeypatch)
    assert "CONFUNDIR" in txt
    assert "actúe sobre el tema" in txt


def test_the_FIRST_case_of_a_batch_gets_no_such_note(monkeypatch):
    """Sensitivity: the first one carries nothing over, so the notice cannot appear—if it appeared every time,
    the judge would forgive memory failures in the only case where they are unequivocally product failures."""
    txt = _prompt({"transcript": [], "mechanism_report": {}}, monkeypatch)
    assert "MEMORIA COMPARTIDA" not in txt


def test_run_passes_the_cases_already_finished_in_this_batch():
    """The notice being present is useless if the runner does not populate it—the failure of “the truth exists but does not reach the
    place where the decision is made,” which has already happened several times in this repo."""
    import inspect

    from tests.use_cases.e2e.agent import run as R

    src = inspect.getsource(R)
    assert "ran_before=[r[\"scenario\"] for r in results]" in src, \
        "el runner no le está pasando al juez los casos ya corridos de esta tanda"
