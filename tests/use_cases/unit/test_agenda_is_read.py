""""Zero appointments persisted" was an invention: the harness had never looked at the agenda.

Measured on 2026-08-20. The judge wrote that on two consecutive rounds of `remember-and-remind-deadline`, and
it reached the engine team as a product defect. They reproduced it and found the opposite. The `state.json` of
the two kept sandboxes confirms it: the 14:39 round had TWO appointments (duplicated) and the 14:43 one had
ONE, "Renovar el seguro del coche" on 2026-08-27. The write happened both times.

The cause was not the judge: the mechanism report simply did not carry the fact, so the model filled the gap.
Now it is READ from the engine and the three situations are stated differently: there are appointments / it is
empty and I checked / I could not look.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import judge as J


def test_when_there_are_meetings_the_judge_is_told_the_write_HAPPENED():
    txt = J.mechanism_facts({"agenda_meetings": [{"title": "Renovar el seguro del coche", "date": "2026-08-27"}]})
    assert "1 CITA(S) ESCRITA(S)" in txt
    assert "Renovar el seguro del coche" in txt and "2026-08-27" in txt
    assert "la escritura OCURRIÓ" in txt
    assert "no digas que no se guardó" in txt


def test_and_still_told_that_DUPLICATES_are_a_real_defect():
    """Without this half the notice would be an amnesty: the 14:39 round wrote the same appointment twice."""
    txt = J.mechanism_facts({"agenda_meetings": [{"title": "renovar el seguro", "date": "2026-08-27"},
                                                 {"title": "Renovar el seguro", "date": "2026-08-27"}]})
    assert "2 CITA(S)" in txt
    assert "DUPLICADOS" in txt


def test_an_EMPTY_agenda_is_stated_as_verified_empty():
    txt = J.mechanism_facts({"agenda_meetings": []})
    assert "VACÍA" in txt and "mirada y confirmada" in txt
    assert "fallo de RESULTADO" in txt


def test_but_UNREADABLE_is_not_the_same_as_empty():
    """The whole distinction: `None` means "I did not look", and nothing can be concluded from it."""
    txt = J.mechanism_facts({"agenda_meetings": None, "agenda_error": "timeout"})
    assert "NO se pudo leer" in txt and "timeout" in txt
    assert "No afirmes que está vacía" in txt
    assert "VACÍA" not in txt


def test_a_run_that_never_looked_says_NOTHING_about_the_agenda():
    """Sensitivity: with the key absent, no sentence about the agenda may appear — neither for nor against."""
    txt = J.mechanism_facts({"families_observed": ["flash"]})
    assert "AGENDA" not in txt.upper().replace("AGENDAS", "")


def test_the_runner_actually_READS_it(monkeypatch):
    """The classic failure: the fact exists and never reaches the place where the decision is made. This checks
    that `_run_scenario` calls the reader and that what it returns ends up INSIDE the report the judge sees."""
    from tests.use_cases.e2e.agent import run as R
    from tests.use_cases.e2e.agent import scenarios as SC

    seen = {}
    monkeypatch.setattr(R.probe_client, "say", lambda t, s, **k: {"reply": "vale", "trace": "t"})
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "session_events", lambda sid: [])
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.probe_client, "widget_rows",
                        lambda wid, key: seen.setdefault("asked", (wid, key)) and None
                        or [{"title": "X", "date": "2026-08-27"}])
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.judgemod, "judge", lambda scn, run: seen.setdefault("mech", run["mechanism_report"]) or {})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "m")

    class _D:
        def __init__(self, scn, persona_name=""): self.done = True
        def opening(self): return "hola"
        def hears(self, t): self.done = True
    monkeypatch.setattr(R.drivermod, "Driver", _D)

    R._run_scenario(SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p",
                                       opening_line="o", success_checks="s", turns=1))
    assert seen.get("asked") == ("agenda", "meetings"), "the runner does not read the engine's agenda"
    assert seen["mech"]["agenda_meetings"] == [{"title": "X", "date": "2026-08-27"}], \
        "what was read never reaches the report the judge sees"
