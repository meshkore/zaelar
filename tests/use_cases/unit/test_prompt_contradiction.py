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
