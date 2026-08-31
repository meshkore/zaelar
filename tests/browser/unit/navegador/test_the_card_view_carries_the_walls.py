"""V2-207 — from outside the process, «the wall was never recorded» and «it was recorded and the turn ignored
it» looked IDENTICAL.

`active_progress()` has built `walls_hit`/`last_wall` since V2-176 and that is what reaches the prompt, but
`_task_view()` — the only view anyone outside this process can read (`GET /widgets/navegador/data?q=<task>`) —
did not expose them. So the use-case harness could see «Access Denied» in the event stream and the task's card
with no trace of any wall, and could not tell which of two OPPOSITE diagnoses applied:

  · `walls_hit == 0` with a wall in the stream  → it was never recorded (a defect of the ANNOTATION);
  · `walls_hit > 0` with the turn saying «sigo con ello» → it arrived and the turn ignored it (a defect of the TURN).

Choosing the wrong one costs a whole round of measurement, which is exactly what happened on
`find-theatre-tickets__es`.

`wall` (the page it is on NOW, recomputed on every capture) and `walls`/`last_wall` (the HISTORY, which survives
the re-route) are deliberately distinct — keeping them apart is the whole point of V2-176.
"""
import importlib

import pytest


@pytest.fixture()
def tasks():
    t = importlib.import_module("widgets.navegador.tasks")
    t._tasks.clear()
    return t


def _view(tid):
    from widgets.navegador import data
    return data.view_data(tid)


def test_a_task_that_hit_a_wall_says_so_in_its_card(tasks):
    tid = tasks.create("entradas de teatro en Madrid")
    tasks.update_view(tid, url="https://www.entradas.com/evento", page_title="",
                      page_text="Access Denied. You don't have permission to access this resource.")
    v = _view(tid)
    assert v["walls_hit"] == 1
    assert "bloqueó el acceso" in (v["last_wall"].get("reason") or "")


def test_the_history_SURVIVES_moving_on_to_another_page(tasks):
    """The half V2-176 exists for: `wall` is recomputed per capture, so a worker that re-routes erases it. If the
    card only carried `wall`, the harness would read a clean task for a run that hit two blocks."""
    tid = tasks.create("entradas de teatro en Madrid")
    tasks.update_view(tid, url="https://www.entradas.com/e", page_title="", page_text="Access Denied.")
    tasks.update_view(tid, url="https://www.elcorteingles.es/entradas/", page_title="", page_text="Resultados")
    v = _view(tid)
    assert v["wall"] == ""              # it is no longer on top of the wall
    assert v["walls_hit"] == 1          # …and yet it still swallowed it


def test_a_clean_task_reports_ZERO_and_not_nothing(tasks):
    """Sensitivity, and the reason the field is a COUNT and not an optional: absent and zero read the same from
    outside, and «I could not look» is a third answer that must not be confused with «there were none»."""
    tid = tasks.create("entradas de teatro en Madrid")
    tasks.update_view(tid, url="https://www.entradas.com/e", page_title="", page_text="Resultados de la búsqueda")
    v = _view(tid)
    assert v["walls_hit"] == 0 and v["last_wall"] == {} and v["wall"] == ""
