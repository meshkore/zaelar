"""Do not close the conversation while its browser task is still alive.

Measured 2026-08-20 in `hotel-under-15-days`: the worker extracted «Exe Sevilla Macarena, 65 €» with a URL at
19:45:29, the last turn came 16 seconds later saying "sigo pendiente", and the task was killed at 19:45:55. The
round ended as a race between the turn budget and the browser — which measures MY clock, not the product.

The grace removes my confound without excusing anything: if the result still never arrives, the finding is
cleaner rather than softer. Bounded, because a case whose task never ends must still end.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import run as R, scenarios as SC, verify as V


def _wire(monkeypatch, *, live: bool, replies=None):
    said = iter(replies or ["y ahora qué"] * 20)
    monkeypatch.setattr(R.probe_client, "say", lambda t, s, **k: {"reply": "sigo con ello", "trace": "t"})
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "session_events", lambda sid: [])
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.probe_client, "widget_rows", lambda wid, key: [])
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.verifymod, "live_navegador_snapshot", lambda *a, **k: "")
    monkeypatch.setattr(R.verifymod, "navegador_task_is_live", lambda: live)
    monkeypatch.setattr(R.watchdogmod, "evaluate",
                        lambda *a, **k: {"action": "continue", "health": "flowing", "reason": ""})
    monkeypatch.setattr(R.judgemod, "judge", lambda *a, **k: {"overall": 3, "scores": {}})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "m")
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    turns = {"n": 0}

    class _D:
        def __init__(self, scn, persona_name=""): self.done = False
        def opening(self): return "hola"
        def hears(self, t): pass
        def reply(self, nudge=""):
            turns["n"] += 1
            return next(said)
    monkeypatch.setattr(R.drivermod, "Driver", _D)
    return turns


def _scn(turns=2):
    return SC.UseCaseScenario(id="x", locale="es", tier=2, persona_brief="p", opening_line="o",
                              success_checks="s", turns=turns, expected_signals=["worker", "widget"])


def test_a_live_task_buys_extra_turns(monkeypatch):
    turns = _wire(monkeypatch, live=True)
    R._run_scenario(_scn(turns=2))
    assert turns["n"] > 1, "la conversación se cerró con el resultado en vuelo"


def test_and_they_are_BOUNDED(monkeypatch):
    """A task that never finishes must not keep a round open forever."""
    turns = _wire(monkeypatch, live=True)
    R._run_scenario(_scn(turns=2))
    assert turns["n"] <= 1 + 3, f"la gracia no tiene tope: {turns['n']} turnos"


def test_a_finished_task_buys_nothing(monkeypatch):
    """Sensitivity: without this, every round in the catalogue gets longer for nothing."""
    turns = _wire(monkeypatch, live=False)
    R._run_scenario(_scn(turns=2))
    assert turns["n"] == 1


def test_a_case_with_no_mechanism_expectation_never_waits(monkeypatch):
    """A purely conversational case has no browser task to wait for."""
    turns = _wire(monkeypatch, live=True)
    scn = SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p", opening_line="o",
                             success_checks="s", turns=2)
    R._run_scenario(scn)
    assert turns["n"] == 1


def test_liveness_reads_the_engines_own_registry(monkeypatch):
    monkeypatch.setattr(V.probe_client, "live_tasks",
                        lambda: [{"kind": "navegador", "status": "working"}])
    assert V.navegador_task_is_live() is True
    monkeypatch.setattr(V.probe_client, "live_tasks", lambda: [{"kind": "navegador", "status": "done"}])
    assert V.navegador_task_is_live() is False
    monkeypatch.setattr(V.probe_client, "live_tasks", lambda: [{"kind": "code", "status": "working"}])
    assert V.navegador_task_is_live() is False


def test_an_unreadable_engine_reads_as_NOT_live(monkeypatch):
    """Conservative on purpose: granting extra turns on a guess would stretch every round in the catalogue."""
    monkeypatch.setattr(V.probe_client, "live_tasks",
                        lambda: (_ for _ in ()).throw(RuntimeError("caído")))
    assert V.navegador_task_is_live() is False
