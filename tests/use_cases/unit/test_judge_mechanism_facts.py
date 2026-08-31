"""The judge cannot contradict its own evidence.

Measured on 2026-08-20 in `cheapest-monitor`: score 1/5 for «inventory hallucination … with no worker traces
validating a real search», citing `missing_signals` — while the mechanism report from the SAME run said
`families_observed: [flash, memory, system, widget, worker]` and `missing_signals: []`. The worker had started
and had finished with real data.

Such a verdict is not merely noise: it sends the engine team to fix something that did not happen, and in a
twelve-hour unattended loop that fills the work board with invented work. The report is now delivered with
its facts in PROSE before the JSON, because an empty list (`"missing_signals": []`) says nothing out loud.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent.judge import mechanism_facts

FULL = {
    "families_observed": ["flash", "memory", "system", "widget", "worker"],
    "expected_signals": ["worker", "widget"],
    "missing_signals": [],
    "navegador_task_id": "",
    "navegador_task": {},
    "n_events": 126,
    "search_health": {"n_search_events": 10, "degraded": False, "reasons": []},
    "scheduled_jobs": {"readable": True, "n_before": 0, "n_after": 0, "created": []},
}


def test_when_nothing_is_missing_it_says_so_out_loud():
    txt = mechanism_facts(FULL)
    assert "NO FALTÓ NINGUNA" in txt
    assert "No afirmes que faltó una señal" in txt


def test_and_when_something_IS_missing_it_says_to_penalise_it():
    """The other half: without this, «close the door on inventing absent signals» and «never penalize the
    mechanism» are indistinguishable, and the judge would let through the failure this harness exists to catch."""
    mech = dict(FULL, families_observed=["flash", "memory"], missing_signals=["worker", "widget"])
    txt = mechanism_facts(mech)
    assert "FALTÓ: worker, widget" in txt
    assert "penaliza" in txt
    assert "NO FALTÓ NINGUNA" not in txt


def test_a_worker_that_started_is_not_a_worker_that_delivered():
    """The nuance that prevents the OPPOSITE error: without it, closing the door on «a signal was missing»
    invites accepting a result merely because the family appears in the list."""
    txt = mechanism_facts(FULL)
    assert "ARRANCÓ" in txt
    assert "NO prueba que devolviera nada aprovechable" in txt


def test_an_empty_scheduler_is_said_to_be_unsupported_but_only_when_it_is_readable():
    assert "no hay respaldo" in mechanism_facts(FULL)
    unreadable = dict(FULL, scheduled_jobs={"readable": False, "created": []})
    txt = mechanism_facts(unreadable)
    assert "no prueba nada" in txt
    assert "no hay respaldo" not in txt


def test_no_browser_task_is_not_automatically_a_failure():
    """A search-and-compare case can be resolved without opening the browser. Saying so avoids the automatic
    1/5 that was measured, without giving free rein: the condition under which it is a failure is named."""
    txt = mechanism_facts(FULL)
    assert "NO es automáticamente un fallo" in txt
    assert "exigía entrar en un sitio concreto" in txt
    with_task = dict(FULL, navegador_task_id="t7")
    assert "Hubo tarea de navegador (t7)" in mechanism_facts(with_task)


def test_no_report_at_all_proves_nothing():
    """Fail-open: if verification could not be performed, the absence of signals is evidence of nothing. The
    opposite would turn every harness failure into a product bug."""
    assert "la AUSENCIA no prueba nada" in mechanism_facts({})


def test_the_prose_reaches_the_prompt_the_judge_actually_reads():
    """The helper's existence is useless if the prompt still carries only the JSON: that is precisely the
    failure of «the truth exists in the task and does not reach the place where the decision is made» that has
    already recurred in V2-145/V2-150."""
    import inspect

    from tests.use_cases.e2e.agent import judge as J

    src = inspect.getsource(J.judge)
    assert "mechanism_facts(mech)" in src
    assert "no lo contradigas" in src


def test_the_judge_is_told_to_answer_in_SPANISH_only():
    """The default judge is glm-4.6, a Chinese model, and on 2026-08-20 it wrote half a finding in Chinese
    (round 16 of V2-176: «sin提供一个具体的输出或障碍说明»). The finding was CORRECT —the system admitted
    having no candidates and prompted waiting— and was unreadable to its sole recipient, the agent that fixes
    things. Evidence that cannot be read is worth the same as not having measured it.
    """
    from tests.use_cases.e2e.agent import judge as J

    assert "IDIOMA" in J._SYS and "CASTELLANO" in J._SYS, (
        "el prompt del sistema del juez no fija idioma: vuelve a poder colar chino en la evidencia")


def test_and_the_system_prompt_is_what_actually_reaches_the_model(monkeypatch):
    """The other half of sensitivity: a constant can remain unwired. What the call RECEIVES is checked,
    not what is written in the module — which is the error this same test used to make,
    asserting based on `inspect.getsource` (where a comment counts the same as the prompt)."""
    from types import SimpleNamespace

    from tests.use_cases.e2e.agent import judge as J

    seen = {}

    def _fake(msgs, **kw):
        seen["msgs"] = msgs
        return ('{"overall":4,"scores":{},"veredicto":"x","hallazgos":[],"mejoras":[]}', "modelo-falso")

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    scn = SimpleNamespace(id="x", tier=1, locale="es", opening_line="hola", goal="g",
                          success_checks=[], expected_signals=[], persona_brief="", turns=4,
                          channel="probe", no_data_scope=None)
    J.judge(scn, {"transcript": [], "mechanism_report": {}})
    system = " ".join(m.get("content", "") for m in seen.get("msgs", []) if m.get("role") == "system")
    assert "CASTELLANO" in system, "la instrucción de idioma no llega a la llamada"
