"""«Cero citas persistidas» era una invención: el arnés nunca había mirado la agenda.

Medido el 2026-08-20. El juez escribió eso dos rondas seguidas sobre `remember-and-remind-deadline`, y llegó
al equipo del código como fallo del producto. Lo reprodujeron y encontraron lo contrario. Los `state.json` de
los dos sandboxes guardados lo confirman: la ronda de las 14:39 tenía DOS citas (duplicadas) y la de las 14:43
tenía UNA, «Renovar el seguro del coche» el 2026-08-27. La escritura ocurrió las dos veces.

La causa no era el juez: era que el informe de mecanismo no llevaba el dato, así que el modelo rellenaba el
hueco. Ahora se LEE del motor y las tres situaciones se dicen distintas: hay citas / está vacía y lo he
comprobado / no he podido mirar.
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
    """Sin esta mitad el aviso sería una amnistía: la ronda de las 14:39 escribió la misma cita dos veces."""
    txt = J.mechanism_facts({"agenda_meetings": [{"title": "renovar el seguro", "date": "2026-08-27"},
                                                 {"title": "Renovar el seguro", "date": "2026-08-27"}]})
    assert "2 CITA(S)" in txt
    assert "DUPLICADOS" in txt


def test_an_EMPTY_agenda_is_stated_as_verified_empty():
    txt = J.mechanism_facts({"agenda_meetings": []})
    assert "VACÍA" in txt and "mirada y confirmada" in txt
    assert "fallo de RESULTADO" in txt


def test_but_UNREADABLE_is_not_the_same_as_empty():
    """La distinción entera: `None` es «no lo he mirado», y de ahí no se puede concluir nada."""
    txt = J.mechanism_facts({"agenda_meetings": None, "agenda_error": "timeout"})
    assert "NO se pudo leer" in txt and "timeout" in txt
    assert "No afirmes que está vacía" in txt
    assert "VACÍA" not in txt


def test_a_run_that_never_looked_says_NOTHING_about_the_agenda():
    """Sensibilidad: si la clave no está, no puede aparecer una frase sobre la agenda — ni a favor ni en contra."""
    txt = J.mechanism_facts({"families_observed": ["flash"]})
    assert "AGENDA" not in txt.upper().replace("AGENDAS", "")


def test_the_runner_actually_READS_it(monkeypatch):
    """El fallo clásico: el dato existe y no llega al sitio donde se decide. Se comprueba que `_run_scenario`
    llama al lector y que lo que devuelve acaba DENTRO del informe que ve el juez."""
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
        def __init__(self, scn): self.done = True
        def opening(self): return "hola"
        def hears(self, t): self.done = True
    monkeypatch.setattr(R.drivermod, "Driver", _D)

    R._run_scenario(SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p",
                                       opening_line="o", success_checks="s", turns=1))
    assert seen.get("asked") == ("agenda", "meetings"), "el runner no lee la agenda del motor"
    assert seen["mech"]["agenda_meetings"] == [{"title": "X", "date": "2026-08-27"}], \
        "lo leído no llega al informe que ve el juez"
