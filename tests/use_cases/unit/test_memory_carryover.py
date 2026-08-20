"""Una tanda comparte UN motor, así que del tercer caso en adelante zaelar recuerda los anteriores — y eso NO
es un defecto del producto.

Medido el 2026-08-20: `renew-gym-membership__es` bajó a 2/5 con el veredicto «fallos de relevancia en memoria,
mezclando dominios (Netflix/Teatro) al preguntar por el gimnasio». Netflix y Teatro son EXACTAMENTE los dos
casos que corrieron antes que él en la misma tanda. Una instalación nueva no puede hacer eso: el hallazgo era
sobre nuestro montaje, no sobre el agente.

No se puede arreglar borrando la memoria entre casos: eso exige matar el proceso (SQLite en uso) y
`/api/reset/full` relanza el motor — en un sandbox eso es peor que el problema. Así que el hecho se ESTAMPA en
la evidencia y llega al juez antes de que razone, igual que `search_health`. Y con el límite dicho: recordar
otro tema no es un fallo, pero CONFUNDIRSE de tema sí.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import judge as J


def _scn():
    from tests.use_cases.e2e.agent import scenarios as SC
    return SC.UseCaseScenario(id="x", locale="es", tier=2, persona_brief="p",
                              opening_line="o", success_checks="s")


def _prompt(run: dict, monkeypatch) -> str:
    """El prompt REAL que recibe el juez, capturado SIN llamar a ningún modelo.

    Se parchea `llm.judge_call`, que es el único punto por el que el juez habla con un modelo (`judge.py:246`).
    La primera versión de este helper ADIVINABA el nombre de la función y no acertaba, así que devolvía "" y
    encima hacía la llamada de verdad: 12 segundos y coste real por un test unitario.
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
    """La mitad que impide que esto sea una amnistía: recordar otro tema no es un fallo, confundirse de tema sí.
    Sin esta frase, el aviso enseñaría al juez a perdonar justo el fallo que el caso busca."""
    txt = _prompt({"transcript": [], "mechanism_report": {}, "memory_carryover": ["otro-caso"]}, monkeypatch)
    assert "CONFUNDIR" in txt
    assert "actúe sobre el tema" in txt


def test_the_FIRST_case_of_a_batch_gets_no_such_note(monkeypatch):
    """Sensibilidad: el primero no arrastra nada, así que el aviso no puede aparecer — si apareciera siempre,
    el juez perdonaría fallos de memoria en el único caso donde son inequívocamente del producto."""
    txt = _prompt({"transcript": [], "mechanism_report": {}}, monkeypatch)
    assert "MEMORIA COMPARTIDA" not in txt


def test_run_passes_the_cases_already_finished_in_this_batch():
    """Que el aviso exista no sirve si el runner no lo rellena — el fallo de «la verdad existe y no llega al
    sitio donde se decide», que en este repo ya se ha repetido varias veces."""
    import inspect

    from tests.use_cases.e2e.agent import run as R

    src = inspect.getsource(R)
    assert "ran_before=[r[\"scenario\"] for r in results]" in src, \
        "el runner no le está pasando al juez los casos ya corridos de esta tanda"
