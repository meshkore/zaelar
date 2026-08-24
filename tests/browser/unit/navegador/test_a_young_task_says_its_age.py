"""A 21-second-old task must not be spoken of as «lleva un rato» — the AGE is a fact the prompt carries (V2-302).

Measured on `search-buy-guitar__es` round 29 (2026-08-24 23:07:13): the task was 21 seconds old, the turn said
«Lleva un rato sin reportar nada, así que puede que esté costando dar con buenas opciones. ¿Quieres que siga
esperando o prefieres que la pare?» — offering to KILL a task that had barely spawned, and priming the operator
into the downward spiral that ended the round («¿tienes ya algo? si no miro yo» → «déjalo ya») seconds before
the first rows landed. The model had no age fact, so it filled the hole with «un rato».

This is deliberately NOT the V2-145 regression: that incident was the brain having ONLY elapsed seconds and
inventing detail from them («todavía interactuando»). The age travels ALONGSIDE the real facts (site, steps,
milestones) and the face tells the model to use it verbatim — grounding the wording, not replacing the facts.
"""
import pytest

from nucleo.flash import live_blocks as LB
from widgets.navegador import tasks as T


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def _state() -> str:
    return "\n".join(LB.navegador_lines())


def test_the_age_travels_in_active_progress():
    tid = T.create("Busca una guitarra acústica")
    T.set_status(tid, "working")
    rows = T.active_progress()
    assert rows and isinstance(rows[0].get("age_s"), int)
    assert 0 <= rows[0]["age_s"] <= 2, "recién creada: la edad tiene que decir segundos, no un hueco"


def test_a_young_task_shows_its_age_in_seconds():
    tid = T.create("Busca una guitarra acústica")
    T.set_status(tid, "working")
    T._tasks[tid]["created"] = T._tasks[tid]["created"] - 21     # the round-29 age, exactly
    state = _state()
    assert "arrancó hace 21 s" in state


def test_an_old_task_shows_minutes_not_a_wall_of_seconds():
    tid = T.create("Busca hoteles")
    T.set_status(tid, "working")
    T._tasks[tid]["created"] = T._tasks[tid]["created"] - 300
    assert "arrancó hace 5 min" in _state()


def test_the_healthy_face_forbids_the_measured_fillers():
    """The exact three moves of round 29, named in the block: «lleva un rato», «puede que esté costando», and
    offering to stop a task that is just starting."""
    tid = T.create("Busca una guitarra")
    T.set_status(tid, "working")
    state = _state()
    assert "no digas que «lleva un rato»" in state
    assert "puede que esté costando" in state
    assert "NO ofrezcas pararla" in state
    assert "2-3 minutos" in state, "sin el número, «está arrancando» no le dice al modelo cuánto es normal"


def test_the_stalled_and_wall_faces_are_untouched():
    """Sensitivity: a task genuinely stuck (past the stall threshold) must keep its BLOCKED face — the age is
    for the healthy face's wording, never a reason to soften a measured stall."""
    tid = T.create("Busca vuelos")
    T.set_status(tid, "working")
    t = T._tasks[tid]
    t["created"] = t["created"] - 400
    t["last_progress"] = t["created"]
    t["url"] = "https://example.com/x"
    state = _state()
    assert "SIN MOVERSE" in state or "BLOQUEADA" in state
