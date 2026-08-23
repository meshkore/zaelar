"""A driven conversation must never be lost with the judge call.

`book-hotel-night-known__es` came back INFRA three times on 2026-08-20 — three full eight-minute conversations,
each with its mechanism report already built — because the judge got 429/503/504. The third time the retry added
that morning fired visibly ("retrying in 8s", "retrying in 16s") and all three attempts still ate a 504. The
retry was the right fix for a blip; it does nothing for a provider that is simply down.

The data is already measured at that point: only the verdict is missing. So the round is parked on disk and can
be judged later without re-driving it. The exception still propagates, because until somebody judges it the
round is honestly INFRA — parking is not a way to make a failure look measured.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import run as R, scenarios as SC


def _scn():
    return SC.UseCaseScenario(id="parked-case", locale="es", tier=1, persona_brief="p", opening_line="o",
                              success_checks="s", turns=1)


def _run():
    return {"transcript": [{"who": "tester", "text": "hola"}, {"who": "zaelar", "text": "vale"}],
            "mechanism_report": {"families_observed": ["flash"]}, "watchdog_log": []}


def test_a_failed_judge_PARKS_the_round(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(R, "PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "m")
    R._park_for_later(_scn(), _run())
    files = list((tmp_path / "pending").glob("*.json"))
    assert len(files) == 1, "la conversación se perdió con la llamada al juez"
    saved = json.loads(files[0].read_text())
    assert saved["scenario"] == "parked-case"
    assert saved["run"]["transcript"], "sin transcripción no se puede juzgar después"
    assert saved["run"]["mechanism_report"], "sin informe de mecanismo el veredicto no valdría lo mismo"
    assert "code" in saved, "hay que saber QUÉ código midió esa ronda cuando se juzgue mañana"


def test_the_run_still_FAILS_after_parking(monkeypatch):
    """Parking must not turn an unjudged round into a measured one: the exception has to keep propagating."""
    import pytest
    monkeypatch.setattr(R.judgemod, "judge", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("504")))
    monkeypatch.setattr(R, "_park_for_later", lambda *a, **k: None)
    monkeypatch.setattr(R.probe_client, "say", lambda t, s, **k: {"reply": "vale", "trace": "t"})
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "session_events", lambda sid: [])
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.probe_client, "widget_rows", lambda wid, key: [])
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "m")

    class _D:
        def __init__(self, scn, persona_name=""): self.done = True
        def opening(self): return "hola"
        def hears(self, t): self.done = True
    monkeypatch.setattr(R.drivermod, "Driver", _D)
    with pytest.raises(RuntimeError):
        R._run_scenario(_scn())


def test_judging_later_folds_it_in_and_removes_it(tmp_path, monkeypatch, capsys):
    pend = tmp_path / "pending"
    pend.mkdir()
    (pend / "x.json").write_text(json.dumps({"scenario": "hotel-under-15-days", "tier": 2, "channel": "probe",
                                             "run": _run(), "drive_model": "m",
                                             "code": {"sha": "abc1234"}}))
    monkeypatch.setattr(R, "PENDING_DIR", pend)
    monkeypatch.setattr(R.judgemod, "judge", lambda scn, run: {"overall": 4, "scores": {}, "veredicto": "ok"})
    recorded: list = []
    monkeypatch.setattr(R.statusmod, "record", lambda res, **k: recorded.append(res))
    assert R._judge_pending() == 0
    assert recorded and recorded[0][0]["verdict"]["overall"] == 4
    assert not list(pend.glob("*.json")), "una ronda juzgada no puede quedarse en la cola"


def test_a_judge_still_down_KEEPS_the_round(tmp_path, monkeypatch):
    pend = tmp_path / "pending"
    pend.mkdir()
    (pend / "x.json").write_text(json.dumps({"scenario": "hotel-under-15-days", "tier": 2, "channel": "probe",
                                             "run": _run(), "drive_model": "m"}))
    monkeypatch.setattr(R, "PENDING_DIR", pend)
    monkeypatch.setattr(R.judgemod, "judge", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("504")))
    monkeypatch.setattr(R.statusmod, "record", lambda *a, **k: None)
    R._judge_pending()
    assert list(pend.glob("*.json")), "si el juez sigue caído la ronda NO se puede tirar"


def test_a_scenario_that_no_longer_exists_is_not_silently_dropped(tmp_path, monkeypatch, capsys):
    pend = tmp_path / "pending"
    pend.mkdir()
    (pend / "x.json").write_text(json.dumps({"scenario": "ya-no-existe", "run": _run()}))
    monkeypatch.setattr(R, "PENDING_DIR", pend)
    R._judge_pending()
    out = capsys.readouterr().out
    assert "ya no existe en el catálogo" in out
    assert list(pend.glob("*.json")), "no se tira sin decir por qué"
