"""El juez no puede contradecir su propia evidencia.

Medido el 2026-08-20 en `cheapest-monitor`: veredicto 1/5 por «alucinación de inventario … sin trazas de
worker que validen una búsqueda real», citando `missing_signals` — mientras el informe de mecanismo de la
MISMA corrida decía `families_observed: [flash, memory, system, widget, worker]` y `missing_signals: []`. El
worker había arrancado y había terminado con datos reales.

Un veredicto así no es solo ruido: manda al equipo del motor a arreglar algo que no ocurrió, y en un bucle
desatendido de doce horas eso llena el tablero de trabajo inventado. El informe se entrega ahora con sus
hechos en PROSA antes del JSON, porque una lista vacía (`"missing_signals": []`) no dice nada en voz alta.
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
    """La otra mitad: sin esto, «cierra la puerta a inventar señales ausentes» y «nunca penalices el
    mecanismo» son indistinguibles, y el juez dejaría pasar el fallo que este arnés existe para cazar."""
    mech = dict(FULL, families_observed=["flash", "memory"], missing_signals=["worker", "widget"])
    txt = mechanism_facts(mech)
    assert "FALTÓ: worker, widget" in txt
    assert "penaliza" in txt
    assert "NO FALTÓ NINGUNA" not in txt


def test_a_worker_that_started_is_not_a_worker_that_delivered():
    """El matiz que impide el error OPUESTO: sin él, cerrar la puerta a «faltó una señal» invita a dar por
    bueno un resultado solo porque la familia aparece en la lista."""
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
    """Un caso de buscar-y-comparar puede resolverse sin abrir el navegador. Decirlo evita el 1/5 automático
    que se midió, sin dar barra libre: se nombra la condición en la que sí es un fallo."""
    txt = mechanism_facts(FULL)
    assert "NO es automáticamente un fallo" in txt
    assert "exigía entrar en un sitio concreto" in txt
    with_task = dict(FULL, navegador_task_id="t7")
    assert "Hubo tarea de navegador (t7)" in mechanism_facts(with_task)


def test_no_report_at_all_proves_nothing():
    """Fail-open: si la verificación no se pudo hacer, la ausencia de señales no es evidencia de nada. Lo
    contrario convertiría cada fallo de arnés en un bug del producto."""
    assert "la AUSENCIA no prueba nada" in mechanism_facts({})


def test_the_prose_reaches_the_prompt_the_judge_actually_reads():
    """Que el helper exista no sirve de nada si el prompt sigue llevando solo el JSON: es justo el fallo de
    «la verdad existe en la tarea y no llega al sitio donde se decide» que ya se repitió en V2-145/V2-150."""
    import inspect

    from tests.use_cases.e2e.agent import judge as J

    src = inspect.getsource(J.judge)
    assert "mechanism_facts(mech)" in src
    assert "no lo contradigas" in src
