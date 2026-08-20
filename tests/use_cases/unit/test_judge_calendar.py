"""El juez no sabía qué día era, y aun así juzgaba fechas.

Medido el 2026-08-20 (ronda 15 de `remember-and-remind-deadline`): el usuario dijo «el jueves» un JUEVES,
zaelar resolvió el jueves SIGUIENTE (27 de agosto) y puso el aviso el miércoles 26. Es coherente — no se puede
avisar la víspera de algo que es hoy. El juez lo marcó como hallazgo [alta]: «el jueves natural es el 20, el
recordatorio cae 6 días tarde». Ese hallazgo iba camino del equipo del código como fallo del producto.

La causa no era el modelo: era que el prompt no llevaba el calendario. Un juez sin fecha no puede evaluar
fechas, y lo intenta igual.
"""
from __future__ import annotations

import datetime

from tests.use_cases.e2e.agent import judge as J


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p",
                              opening_line="apúntame algo para el jueves", success_checks="s")


def _prompt(monkeypatch) -> str:
    """El prompt REAL que le llega al juez, sin llamar a ningún modelo: se parchea `llm.judge_call`, que es su
    único punto de contacto con uno."""
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "modelo-de-prueba"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), {"transcript": [], "mechanism_report": {}})
    return seen.get("user", "")


def test_the_judge_is_told_todays_date_and_weekday(monkeypatch):
    txt = _prompt(monkeypatch)
    hoy = datetime.date.today()
    assert hoy.isoformat() in txt, "el juez no sabe en qué fecha está"
    assert J._DIAS[hoy.weekday()] in txt, "le falta el DÍA DE LA SEMANA, que es lo que resuelve «el jueves»"


def test_and_told_that_a_weekday_means_the_NEXT_one(monkeypatch):
    """La regla concreta que habría evitado el falso positivo: si hoy es jueves, «el jueves» es el siguiente."""
    txt = _prompt(monkeypatch)
    assert "PRÓXIMO" in txt
    assert "la semana siguiente" in txt


def test_and_told_NOT_to_invent_a_finding_when_the_date_fits(monkeypatch):
    """Sin esta mitad, el aviso solo cambia CUÁL fecha prefiere el juez en vez de callarlo cuando no hay fallo."""
    txt = _prompt(monkeypatch)
    assert "solo está MAL si contradice" in txt
    assert "NO es un hallazgo" in txt


def test_the_reminder_rule_is_about_ORDER_not_about_which_day(monkeypatch):
    """El hallazgo falso decía «cae 6 días tarde». Lo único que importa es que el aviso vaya ANTES del evento."""
    txt = _prompt(monkeypatch)
    assert "va ANTES del evento" in txt


def test_with_search_down_REFUSING_to_answer_scores_HIGH(monkeypatch):
    """Lo preguntó el equipo del código antes de arriesgar una regresión (2026-08-20), y tenían razón.

    Su arreglo de `quick-fact-opening-hours` hace que, con la búsqueda caída, el turno sustituya la cifra
    improvisada por «no he podido comprobarlo, prefiero no darte un dato inventado». El `success_checks` del
    caso pide los dos datos contestados, así que el juez lo habría marcado como fallo de resultado — y habría
    castigado exactamente la conducta que el caso existe para conseguir. Es el mismo principio que ya rige los
    casos topados por credenciales: decir qué falta puntúa, fingir es lo grave.
    """
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "modelo-de-prueba"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), {"transcript": [], "mechanism_report": {
        "search_health": {"degraded": True, "reasons": [("captcha", 3)], "n_search_events": 3}}})
    txt = seen["user"]
    assert "se NEGÓ a dar un dato" in txt
    assert "puntúa ALTO" in txt
    assert "describe el caso con el entorno SANO" in txt


def test_but_a_healthy_search_gets_no_such_pass(monkeypatch):
    """Sensibilidad: con la búsqueda SANA, negarse a contestar sí es un fallo de resultado y el aviso no puede
    aparecer — si apareciera siempre, el arnés perdonaría a un agente que no busca nunca."""
    seen: dict[str, str] = {}

    def _fake(msgs, **kw):
        seen["user"] = next((m["content"] for m in msgs if m.get("role") == "user"), "")
        return ('{"scores":{"naturalidad":3,"adaptacion":3,"resultado":3,"mecanismo":3,"eficiencia":3},'
                '"veredicto":"x","findings":[],"improvements":[]}'), "m"

    monkeypatch.setattr(J.llm, "judge_call", _fake)
    J.judge(_scn(), {"transcript": [], "mechanism_report": {
        "search_health": {"degraded": False, "n_search_events": 4}}})
    assert "se NEGÓ a dar un dato" not in seen["user"]
