"""The prompt cannot claim the same errand is running and finished at the same time.

Measured on 2026-08-20 (V2-222): a first attempt failed, was archived as ended, and auto-resume
relaunched the SAME errand under a new id — so both blocks told the truth about different sessions
while the operator had one errand. Every obedience number taken over such a turn is void, which is
why the harness has to see this by itself instead of waiting for someone to read eight prompts by
hand.
"""
from tests.use_cases.e2e.agent import verify

_LIVE = ("TAREAS DE FONDO EN CURSO (los brain workers las están resolviendo; NO reinicies ni digas "
         "que ya está): «Busca hoteles de 4 estrellas para 2 personas, 4 noches, con » — abriendo "
         "una página… [paso 2/5, 40%] (llevas 64s)")
_DONE = ("TAREAS DE FONDO — YA ACABADAS: «Busca hoteles de 4 estrellas para 2 personas, 4 no» FALLÓ. "
         "El operador NO LO SABE: está esperando un resultado que ya no va a llegar.")


def test_the_same_errand_alive_and_dead_is_reported():
    rows = [{"turn": 3, "live_line": _LIVE, "failed_task_line": _DONE}]
    hits = verify.prompt_contradictions(rows)
    assert len(hits) == 1
    assert hits[0]["turn"] == 3
    assert hits[0]["objective"].startswith("Busca hoteles de 4 estrellas")


def test_truncation_width_does_not_hide_it():
    """The two blocks cut the objective at different widths; equality would miss every real case."""
    rows = [{"turn": 0,
             "live_line": "TAREAS DE FONDO EN CURSO: «Reserva una mesa para cuatro el viernes por »",
             "failed_task_line": "TAREAS DE FONDO — YA ACABADAS: «Reserva una mesa para cuatro» FALLÓ."}]
    assert verify.prompt_contradictions(rows)


def test_two_different_errands_are_not_a_contradiction():
    rows = [{"turn": 0,
             "live_line": "TAREAS DE FONDO EN CURSO: «Busca hoteles de 4 estrellas en Sevilla»",
             "failed_task_line": "TAREAS DE FONDO — YA ACABADAS: «Mira el tiempo del fin de semana» FALLÓ."}]
    assert verify.prompt_contradictions(rows) == []


def test_a_short_shared_prefix_is_not_enough():
    """«Busca» matching «Busca» would flag every unrelated search as a contradiction."""
    rows = [{"turn": 0,
             "live_line": "TAREAS DE FONDO EN CURSO: «Busca»",
             "failed_task_line": "TAREAS DE FONDO — YA ACABADAS: «Busca» FALLÓ."}]
    assert verify.prompt_contradictions(rows) == []


def test_no_finished_block_means_nothing_to_contradict():
    rows = [{"turn": 0, "live_line": _LIVE, "failed_task_line": ""}]
    assert verify.prompt_contradictions(rows) == []


# ── SECOND family: «has results» and «queued, nothing yet» in the SAME prompt ──────────────────────────
# Measured on `search-secondhand-monitor__es` (2026-08-23 23:24), reproduced VERBATIM from the round's
# recorded `prompt_context` rows. The judge filed turns 4, 5 and 6 as three [alta] acts of disobedience —
# «tenía la entrega lista y no la dio» — over a prompt that told the turn both things at once.

_TASK_WITH_RESULTS = (
    "NAVEGADOR — YA EN CURSO (1): «Buscar un monitor de segunda mano de al menos 27 pulgadas por menos de» "
    "— en es.wallapop.com, 1 pasos dados · YA TIENE RESULTADOS. «Buscar un monitor de segunda mano de al "
    "menos 27 p» YA TRAJO ALGO: no está bloqueada ni esperando, tiene resultados en la hoja. DÁSELOS en")
_LIVE_QUEUED = (
    "TAREAS DE FONDO EN CURSO (los brain workers las están resolviendo; NO reinicies ni digas que ya "
    "está): «Buscar un monitor de segunda mano de al menos 27 pulgadas po» — en cola (llevas 23s). Si el "
    "operador pregunta el estado, di el PASO concreto y el tiempo que lleva")


def test_has_results_against_still_queued_is_reported():
    rows = [{"turn": 4, "task_line": _TASK_WITH_RESULTS, "live_line": _LIVE_QUEUED}]
    hits = verify.prompt_contradictions(rows)
    assert len(hits) == 1
    assert hits[0]["kind"] == "found_and_empty"
    assert hits[0]["turn"] == 4


def test_a_live_block_that_names_the_candidates_is_not_contradicting():
    """The engine fix (V2-222 third face) makes the two blocks agree — and then there is nothing to report.

    This is the whole point of the detector: it has to go quiet the moment the prompt stops arguing with
    itself, or every future round reads as a prompt fault and the obedience reading stays void forever.
    """
    live = _LIVE_QUEUED.replace("— en cola (llevas 23s)",
                                "— YA HA ENCONTRADO 35 candidato(s), están en la hoja (llevas 23s)")
    rows = [{"turn": 4, "task_line": _TASK_WITH_RESULTS, "live_line": live}]
    assert verify.prompt_contradictions(rows) == []


def test_a_browser_task_without_results_is_not_contradicting():
    task = _TASK_WITH_RESULTS.replace("· YA TIENE RESULTADOS.", "·")
    rows = [{"turn": 4, "task_line": task, "live_line": _LIVE_QUEUED}]
    assert verify.prompt_contradictions(rows) == []


def test_results_on_ANOTHER_errand_is_not_a_contradiction():
    """Two live errands is the normal case: one having results says nothing about the other."""
    live = _LIVE_QUEUED.replace("Buscar un monitor de segunda mano de al menos 27 pulgadas po",
                                "Mira el tiempo del fin de semana en Bilbao")
    rows = [{"turn": 4, "task_line": _TASK_WITH_RESULTS, "live_line": live}]
    assert verify.prompt_contradictions(rows) == []


def test_the_judge_tells_the_two_families_apart():
    """Naming the wrong one sends whoever reads it to the wrong block of the prompt."""
    from tests.use_cases.e2e.agent import judge
    mech = {"families_observed": ["worker"], "expected_signals": [], "missing_signals": [],
            "prompt_contradictions": [
                {"turn": 3, "objective": "Busca hoteles de 4 estrellas", "n": 1,
                 "kind": "alive_and_finished"},
                {"turn": 4, "objective": "Buscar un monitor de segunda mano", "n": 1,
                 "kind": "found_and_empty"}]}
    facts = judge.mechanism_facts(mech)
    assert "YA ACABADO/FALLIDO" in facts
    assert "YA TENÍA RESULTADOS" in facts
    assert "(turnos 3)" in facts and "(turnos 4)" in facts
