"""`ingest` has to follow the SANDBOX, and that is not a detail — it decides whether half the catalogue can
pass at all.

The harness called the probe with `ingest=False` everywhere, for a reason that was right when it was written:
a test conversation has no business in the OPERATOR's real long-term memory. Once the suite moved to a
throwaway engine that reason stopped applying, and the leftover default became a measurement bug: the
developer pointed out (2026-08-20) that `remember-and-remind-deadline`'s memory half was UNREACHABLE — the
agent was being graded on a write the harness itself was suppressing.

The fix is not seeding `ingest=True` for one case, and not dropping the protection either: `ingest=sandboxed`.
Against the operator's live engine the original reason still stands.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import judge as judgemod, llm as llmmod, probe_client
from tests.use_cases.e2e.agent import run as R, verify as verifymod
from tests.use_cases.e2e.agent import driver as drivermod


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x-ingest", locale="es", tier=1, persona_brief="p",
                              opening_line="hola", success_checks="s", turns=1)


class _FakeDriver:
    """Un turno y fuera: lo que se mide aquí es CÓMO se llama al probe, no la conversación."""
    def __init__(self, scenario):
        self.done = False

    def opening(self) -> str:
        return "hola"

    def hears(self, text: str) -> None:
        self.done = True


@pytest.fixture
def calls(monkeypatch):
    """Corre `_run_scenario` de verdad con TODO lo que sale a la red parcheado, y devuelve los kwargs con los
    que se llamó al probe. Nada de leer el código fuente: un comentario satisfaría a un grep, y esa trampa ya
    se ha caído dos veces en esta suite."""
    seen: list[dict] = []

    def _say(text, session, **kw):
        seen.append(dict(kw))
        return {"reply": "vale", "trace": "t"}

    monkeypatch.setattr(R.probe_client, "say", _say)
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "session_events", lambda sid: [])
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.drivermod, "Driver", _FakeDriver)
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.judgemod, "judge", lambda *a, **k: {"overall": 3})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "modelo-de-prueba")
    return seen


def test_in_a_sandbox_the_conversation_IS_ingested(calls):
    R._run_scenario(_scn(), sandboxed=True)
    assert calls, "no se llamó al probe"
    assert calls[0].get("ingest") is True, \
        "en sandbox la conversación tiene que escribirse: sin eso, un caso de «acuérdate de esto» no puede pasar"


def test_against_the_LIVE_engine_it_is_not(calls):
    R._run_scenario(_scn(), sandboxed=False)
    assert calls[0].get("ingest") is False, \
        "contra el motor del operador sigue en pie la razón original: no dejar conversaciones de test en su memoria"


def test_the_default_is_the_SAFE_one(calls):
    """Si alguien llama a `_run_scenario` sin decir nada, no puede acabar escribiendo en la memoria real."""
    R._run_scenario(_scn())
    assert calls[0].get("ingest") is False


def test_and_the_batch_actually_PASSES_the_flag_down(monkeypatch):
    """El fallo clásico de este repo: la verdad existe y no llega al sitio donde se decide. `_run_batch` sabe
    si hay sandbox; si no lo baja, el arreglo de arriba no se aplica nunca en una corrida real."""
    seen: list[dict] = []
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **kw: seen.append(kw) or {
        "scenario": scn.id, "tier": 1, "channel": "probe", "run": {}, "verdict": {"overall": 3},
        "drive_model": "m"})
    monkeypatch.setattr(R.statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(R.reportmod, "build", lambda *a, **k: R.config.RUNS_DIR / "x.md")
    monkeypatch.setattr(R.initiativemod, "file_failure", lambda *a, **k: None)
    R._run_batch([_scn()], sandboxed=True, args_no_file=True)
    assert seen and seen[0].get("sandboxed") is True
