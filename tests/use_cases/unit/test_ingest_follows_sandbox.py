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
    """One turn and out: what is measured here is HOW the probe is called, not the conversation."""
    def __init__(self, scenario):
        self.done = False

    def opening(self) -> str:
        return "hola"

    def hears(self, text: str) -> None:
        self.done = True


@pytest.fixture
def calls(monkeypatch):
    """Runs the real `_run_scenario` with EVERYTHING that goes to the network patched out, and returns the
    kwargs the probe was called with. No reading the source: a comment would satisfy a grep, and this suite has
    already fallen into that trap twice."""
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
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "test-model")
    return seen


def test_in_a_sandbox_the_conversation_IS_ingested(calls):
    R._run_scenario(_scn(), sandboxed=True)
    assert calls, "the probe was never called"
    assert calls[0].get("ingest") is True, \
        "in a sandbox the conversation must be written: without it, a \"remember this\" case cannot pass"


def test_against_the_LIVE_engine_it_is_not(calls):
    R._run_scenario(_scn(), sandboxed=False)
    assert calls[0].get("ingest") is False, \
        "against the operator's engine the original reason still stands: no test conversations in their memory"


def test_the_default_is_the_SAFE_one(calls):
    """If someone calls `_run_scenario` saying nothing, it must not end up writing to the real memory."""
    R._run_scenario(_scn())
    assert calls[0].get("ingest") is False


def test_and_the_batch_actually_PASSES_the_flag_down(monkeypatch):
    """This repo's classic failure: the truth exists and never reaches the place where the decision is made.
    `_run_batch` knows whether there is a sandbox; if it does not pass that down, the fix above never applies
    in a real run."""
    seen: list[dict] = []
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **kw: seen.append(kw) or {
        "scenario": scn.id, "tier": 1, "channel": "probe", "run": {}, "verdict": {"overall": 3},
        "drive_model": "m"})
    monkeypatch.setattr(R.statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(R.reportmod, "build", lambda *a, **k: R.config.RUNS_DIR / "x.md")
    monkeypatch.setattr(R.initiativemod, "file_failure", lambda *a, **k: None)
    R._run_batch([_scn()], sandboxed=True, args_no_file=True)
    assert seen and seen[0].get("sandboxed") is True
