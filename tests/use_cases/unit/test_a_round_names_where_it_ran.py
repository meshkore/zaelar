"""A round says WHERE it ran and WHICH trace each turn was (V2-856): the workspace of the engine it measured, that
engine's URL, and the corr_id the engine gave every turn — written into the round itself. Before this the Observatory
guessed the workspace by time and the turn by its text, and a trimmed line or a batch that reused one sandbox opened
the wrong evidence without saying so.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import config
from tests.use_cases.e2e.agent import run as R


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x-where", locale="es", tier=1, persona_brief="p",
                              opening_line="hola", success_checks="s", turns=1)


class _OneTurn:
    def __init__(self, scenario, persona_name=""):
        self.done = False

    def opening(self) -> str:
        return "hola"

    def hears(self, text: str) -> None:
        self.done = True


@pytest.fixture
def driven(monkeypatch):
    """The real `_run_scenario`, network patched out; the engine answers each turn with its trace id."""
    monkeypatch.setattr(R.probe_client, "say", lambda text, session, **kw: {"reply": "vale", "trace": "T1·abcd"})
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.drivermod, "Driver", _OneTurn)
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.judgemod, "judge", lambda *a, **k: {"overall": 3})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "test-model")
    monkeypatch.setattr(config, "ZAELAR_URL", "http://127.0.0.1:43999")
    monkeypatch.setattr(R.probe_client, "session_events",
                        lambda sid: [{"id": 7, "cat": "widget", "kind": "widget", "label": "show", "ts_ms": 9e15}])
    bus: list[tuple[str, dict]] = []
    monkeypatch.setattr(R.busmod, "_emit", lambda ty, **f: bus.append((ty, f)))
    out = R._run_scenario(_scn())
    out["_bus"] = bus
    return out


def test_both_rows_of_an_exchange_carry_the_turn_s_corr_id(driven) -> None:
    rows = driven["run"]["transcript"]
    assert [(r["who"], r.get("corr_id")) for r in rows[:2]] == [("tester", "T1·abcd"), ("zaelar", "T1·abcd")]


def test_the_round_names_the_engine_it_measured(driven) -> None:
    assert driven["run"]["engine_url"] == "http://127.0.0.1:43999"


def test_the_workspace_is_the_one_whose_db_the_round_read(monkeypatch, tmp_path) -> None:
    ws = tmp_path / "20261106-090000-es"
    monkeypatch.setattr(config, "SANDBOX_DB", str(ws / "memory" / "_data" / "sandbox.db"))
    assert R._where_it_ran()["workspace"] == str(ws.resolve())
    monkeypatch.setattr(config, "SANDBOX_DB", "")
    assert "workspace" not in R._where_it_ran(), "no sandbox DB, no workspace: never a guessed one"


def test_the_mechanism_is_published_after_every_turn_not_only_at_the_end(driven) -> None:
    live = [f for ty, f in driven["_bus"] if ty == "mechanism.turn"]
    assert live and live[0]["turn"] == 0 and live[0]["corr_id"] == "T1·abcd" and live[0]["seen"] == ["widget"]


def test_each_signal_points_at_the_first_event_that_proved_it() -> None:
    from tests.use_cases.e2e.agent import verify
    evs = [{"id": 3, "cat": "flash", "corr_id": "T1"}, {"id": 4, "cat": "widget", "corr_id": "T1", "label": "show"},
           {"id": 9, "cat": "widget", "corr_id": "T2"}]
    got = verify.signal_evidence(evs, ["widget", "worker"])
    assert got == {"widget": {"id": 4, "corr_id": "T1", "label": "show"}}, "a signal that never fired has no entry"

