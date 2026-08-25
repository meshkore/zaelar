"""«SIN MOVERSE de esa página» exige que HAYA una página (V2-308).

Measured on the 04:35 round (2026-08-25): the guitar task had reported no steps and had no URL, `stalled_s`
counts from `last_progress or created` — so a task that has not taken its FIRST step accrues "stall" from
birth and crossed the 120 s threshold while still starting up. The block then contradicted itself inside one
line: «AÚN NO HA REPORTADO NINGÚN PASO (no sabes si está pensando o atascada)» followed by «ESTÁ BLOQUEADA …
es un HECHO medido». The model believed the strong half, told the operator the search was dead and offered to
relaunch it FOUR times while the operator forbade it — the round scored 2/1/1/2/1.

It is V2-152 from the other side: there we asserted the task had opened nothing; here we assert it got stuck
on a page that does not exist. With no URL and no steps there is no stall to measure — there is a task with
no signal yet, and that already has its own wording in the healthy branch (plus the age, V2-302).
"""
import pytest

from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def _old_task(*, url: str = "", steps: int = 0) -> str:
    tid = T.create("Busca una guitarra acústica de segunda mano")
    T.set_status(tid, "working")
    t = T._tasks[tid]
    t["created"] = t["created"] - 480          # 8 min, the measured age
    t["last_progress"] = t["created"]
    if url:
        t["url"] = url
    if steps:
        t["events"] = [{"text": f"paso {i}"} for i in range(steps)]
    return tid


def _state() -> str:
    return "\n".join(LB.navegador_lines())


def test_no_page_and_no_steps_is_not_a_stall():
    _old_task()
    state = _state()
    assert "SIN MOVERSE" not in state, "sin página no hay atasco que medir — es una tarea sin señal"
    assert "ESTÁ BLOQUEADA" not in state
    assert "arrancó hace 8 min" in state, "la edad sigue siendo el hecho honesto que sí se dice"


def test_and_it_does_not_offer_to_abandon_the_search():
    """El daño concreto: la salida de la cara bloqueada («probar en otro sitio, que entre él, o dejarlo»)
    sobre una tarea que solo está arrancando es lo que hizo ofrecer el relanzamiento cuatro veces."""
    _old_task()
    state = _state()
    assert "o dejarlo" not in state
    assert "NO va a terminar sola" not in state


def test_a_task_ON_a_page_that_stops_moving_IS_still_stuck():
    """Sensibilidad, y es la mitad que protege a V2-167: con página delante, un atasco medido sigue siendo un
    atasco y sigue diciéndose con su salida."""
    _old_task(url="https://es.wallapop.com/search?keywords=guitarra")
    state = _state()
    assert "SIN MOVERSE" in state and "ESTÁ BLOQUEADA" in state


def test_steps_without_a_url_also_count_as_something_to_stall_on():
    """Un worker que reportó pasos y luego se calló sí tiene movimiento del que hablar, aunque la captura no
    haya dejado url (una tarea puede reportar fase antes de que el navegador registre página)."""
    _old_task(steps=3)
    assert "SIN MOVERSE" in _state()
