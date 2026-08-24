"""V2-150 (`restaurant-tonight-madrid`) — la tarea había TERMINADO y el turno seguía contando que iba.

El informe decía `status=done url=` y zaelar: «los procesos siguen en marcha — llevan casi 5 minutos». No es el
modelo inventando por gusto: el cerebro solo ve tareas ACTIVAS (`active_summaries`/`active_progress`), así que en
cuanto esta acabó **desapareció del estado**. No quedaba ningún hecho diciendo que había terminado, y menos que
había terminado vacía — se le había quitado de delante lo único que podía contradecirle, y el turno rellenó el
hueco con lo que aún tenía: el worker.

Y el mismo run había DESCUBIERTO «Casa Lucio solo acepta reservas por teléfono» con los números. El operador se
enteró en el último turno, cuando pidió pararlo. El hito estaba en la tarea desde el principio; al cerebro le
llegaba un CONTADOR de pasos, y un número no se puede decir en voz alta.

Mismo remedio que `silent_s` (V2-131) y que la página actual (V2-145), un paso más: un FINAL es un hecho, y una
tarea que acabó sin resultado es el más útil de los tres.
"""
from __future__ import annotations

import pytest

from nucleo.flash import prompt
from widgets.navegador import tasks as nt


def _line(prefix: str) -> str:
    return next((l for l in prompt.live_state().splitlines() if l.startswith(prefix)), "")


@pytest.fixture
def no_live_tasks(monkeypatch):
    monkeypatch.setattr(nt, "active_summaries", lambda limit=3: [])
    monkeypatch.setattr(nt, "active_progress", lambda limit=3: [])


def _finished(**over):
    row = {"id": "t1", "goal": "reservar mesa en Casa Lucio", "status": "done", "url": "",
           "has_results": False, "last_event": "", "ago_s": 30}
    row.update(over)
    return [row]


def test_a_task_that_ended_empty_says_so(no_live_tasks, monkeypatch):
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: _finished())
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "terminó SIN traer nada" in line
    assert "Eso YA NO está en marcha" in line


def test_a_task_that_ended_WITH_something_says_that_instead(no_live_tasks, monkeypatch):
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: _finished(has_results=True))
    assert "terminó CON resultado" in _line("NAVEGADOR — YA TERMINADO")


def test_what_it_last_saw_travels_with_the_ending(no_live_tasks, monkeypatch):
    """«Solo acepta reservas por teléfono» ES el resultado del encargo, aunque no sea el que se esperaba."""
    monkeypatch.setattr(nt, "recently_finished",
                        lambda now=None, limit=3: _finished(
                            last_event="Casa Lucio solo acepta reservas por teléfono: 91 365 82 17"))
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "91 365 82 17" in line
    assert "DÁSELO: es el resultado" in line


def test_with_nothing_finished_the_line_does_not_appear(no_live_tasks, monkeypatch):
    """Coste CERO cuando no hay nada que decir — como el resto de marcas de este bloque."""
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: [])
    assert _line("NAVEGADOR — YA TERMINADO") == ""


def test_a_live_task_now_carries_its_last_milestone(monkeypatch):
    monkeypatch.setattr(nt, "active_summaries", lambda limit=3: [("t9", "reservar mesa en Casa Lucio")])
    monkeypatch.setattr(nt, "active_progress",
                        lambda limit=3: [{"id": "t9", "goal": "x", "url": "https://www.thefork.es/casa-lucio",
                                          "phase": "", "steps": 3,
                                          "last_event": "el restaurante solo reserva por teléfono",
                                          "awaiting_login": False}])
    monkeypatch.setattr(nt, "recently_finished", lambda now=None, limit=3: [])
    line = _line("NAVEGADOR — YA EN CURSO")
    assert "solo reserva por teléfono" in line
    assert "3 pasos dados" in line


# ── the registry side ───────────────────────────────────────────────────────────────────────────────────────
def test_recently_finished_reports_what_the_task_ended_with():
    tid = nt.create("reservar mesa en Casa Lucio")
    nt.add_event(tid, "Casa Lucio solo acepta reservas por teléfono: 91 365 82 17")
    assert nt.active_progress()[0]["last_event"].startswith("Casa Lucio solo acepta")
    nt.finish(tid, "done")
    rows = [r for r in nt.recently_finished() if r["id"] == tid]
    assert rows and rows[0]["status"] == "done"
    assert rows[0]["has_results"] is False
    assert "91 365 82 17" in rows[0]["last_event"]
    assert not [t for t in nt.active_progress() if t["id"] == tid]   # y ya NO está entre las vivas


def test_an_old_ending_stops_being_reported():
    """Suficiente para cubrir el turno del «¿lo conseguiste?», no para hablar del recado de ayer."""
    import time as _t
    tid = nt.create("un encargo viejo")
    nt.finish(tid, "done")
    assert [r for r in nt.recently_finished() if r["id"] == tid]
    later = _t.time() + nt.JUST_FINISHED_S + 60
    assert not [r for r in nt.recently_finished(now=later) if r["id"] == tid]


# ── V2-299: «SIN traer nada» se decidía por el registro de la TAREA, y la hoja es quien fía ─────────────────
#
# Medido el 2026-08-24 (segunda familia del arnés: 7 rondas con las filas en la hoja 42-209 s antes del último
# turno): la tarea terminaba, `has_results` era False porque nadie llegó a llamar a `set_results` —worker
# muerto, relevo—, y esta cara decía «terminó SIN traer nada» con 21 filas CON NOMBRE en la hoja. Un paso peor
# que la desaparición que arregló V2-150: aquello era un hueco, esto es una mentira activa en el prompt.
#
# Estos tests montan la CADENA REAL (tarea en el registro + filas por `intake.push` + `recently_finished` de
# verdad) en vez de parchear `_sheet_top_rows`: el cableado es lo que se mide, y parchear la costura bajo test
# dejaría verde un desarme que la quitara.

@pytest.fixture
def _isolated_sheet(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(nt, "_tasks", {})
    store._last_hash.clear()
    yield
    store._last_hash.clear()


def _done_task_with_sheet(rows, status="done", **over):
    import time as _time

    from widgets.results import intake
    t = {"id": "t1", "goal": "una guitarra acústica de segunda mano", "sheet": "hoja-x",
         "url": "https://es.wallapop.com", "status": status, "finished": _time.time() - 30, "events": []}
    t.update(over)
    nt._tasks["t1"] = t
    if rows:
        intake.push(rows, sheet="hoja-x")


def test_rows_in_the_sheet_beat_an_empty_task_record(_isolated_sheet):
    """El caso medido: `set_results` nunca corrió, la hoja tiene las filas. La hoja gana — y como la tarea ya
    TERMINÓ, decir «en la hoja» es un hecho, no la afirmación de pantalla que V2-278 prohíbe en vuelo."""
    _done_task_with_sheet([{"title": "Fender CD-60", "price": "120 €", "url": "https://x/1"},
                           {"title": "Crafter FX 550", "price": "140 €", "url": "https://x/2"}])
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "terminó SIN traer nada" not in line, \
        "con filas con nombre en la hoja, «SIN traer nada» es una mentira activa en el prompt"
    assert "Fender CD-60" in line and "120 €" in line, \
        "la orden de nombrarlo sin las filas delante es la trampa de V2-298 otra vez"
    assert "en la hoja de resultados" in line


def test_a_task_that_ended_empty_STILL_says_so(_isolated_sheet):
    """La otra mitad de V2-150 no se pierde: sin filas y sin resultado, «terminó SIN traer nada» sigue siendo
    el hecho más útil de los tres."""
    _done_task_with_sheet([])
    assert "terminó SIN traer nada" in _line("NAVEGADOR — YA TERMINADO")


def test_a_CANCELLED_task_does_not_get_rows_pinned_on_it(_isolated_sheet):
    """Pararse no es acabar (V2-196): el operador dijo que parásemos, y colgarle filas a la cancelada invita a
    tratarlas como un final que no ocurrió. El alcance del arreglo es la TERMINADA, y solo ella."""
    _done_task_with_sheet([{"title": "Fender CD-60", "price": "120 €"}], status="cancelled")
    line = _line("NAVEGADOR — YA TERMINADO")
    assert "se PARÓ (cancelada)" in line
    assert "Fender CD-60" not in line
