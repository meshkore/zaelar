"""Todo estado de una tarea de navegador pertenece a UN conjunto: viva o terminada (V2-197).

`active_summaries()` filtraba por `("queued","working","needs_input")` y `recently_finished()` por
`("done","failed")`, cada uno con su lista a mano. **Un estado que no está en ninguna de las dos es una tarea
que el estado vivo no menciona EN ABSOLUTO** — ni viva ni terminada— y entonces el modelo sigue con lo último
que sabía, que es lo correcto cuando nadie le dice otra cosa.

Ese hueco costó `cancelled` (V2-196, medido en `find-theatre-tickets__es`: «bucle de espera infinito sobre una
tarea que ya falló»). Y en cuanto la enumeración pasó a estar en un solo sitio apareció que **`open` llevaba
en el mismo hueco desde siempre**, puesto por `owner.py` cada vez que se abre una página PARA el operador: le
abres Booking, luego pregunta «¿lo tienes?», y el estado no dice nada de esa pestaña.

Dos listas que hay que mantener sincronizadas son dos listas que no lo van a estar. Este test es el que lo
impide, y no mira las listas: mira el CÓDIGO, y falla si alguien estrena un estado sin clasificarlo.
"""
from __future__ import annotations

import re
from pathlib import Path

from widgets.navegador import tasks

ROOT = Path(__file__).resolve().parents[4]
_SET_STATUS = re.compile(r"set_status\(\s*[^,]+,\s*[\"']([a-z_]+)[\"']")


def _statuses_written_anywhere() -> set[str]:
    found: set[str] = set()
    for d in ("nucleo", "widgets", "voice", "server", "connectors"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            try:
                found |= set(_SET_STATUS.findall(py.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    return found


def test_the_two_sets_do_not_overlap():
    assert not (tasks.LIVE_STATES & tasks.ENDED_STATES)


def test_every_status_the_code_writes_is_classified():
    unclassified = sorted(_statuses_written_anywhere() - tasks.LIVE_STATES - tasks.ENDED_STATES)
    assert not unclassified, (
        f"estados de tarea que no están ni en LIVE_STATES ni en ENDED_STATES: {unclassified}. "
        "Una tarea en ese estado NO aparece en el estado vivo —ni viva ni terminada— y el modelo sigue "
        "contando lo último que supo. Clasifícalo, y si es un final decide cómo se DICE en "
        "`nucleo/flash/prompt.py` (un final que suena igual que otro distinto tampoco sirve).")


def test_open_is_an_ENDED_state_and_says_what_it_is():
    """El que estaba en el hueco. No es un fracaso ni un resultado: es una pestaña que sigue delante suyo."""
    from nucleo.flash import prompt as _p

    assert "open" in tasks.ENDED_STATES
    tasks._tasks.clear()
    tid = tasks.create("Abrir Booking")
    tasks.set_status(tid, "working")
    tasks.update_view(tid, url="https://www.booking.com/")
    tasks.set_status(tid, "open")
    try:
        state = _p.live_state()
        assert "está ABIERTA en pantalla" in state
        assert "terminó SIN traer nada" not in state
    finally:
        tasks._tasks.clear()


def test_entering_ANY_ended_state_stamps_when_it_ended():
    """`recently_finished()` filtra por una ventana de tiempo, así que un final sin hora es un final que nadie
    puede fechar — y desaparece igual. El sello lo pone ENTRAR en un final, no cada función por su cuenta."""
    for st in sorted(tasks.ENDED_STATES):
        tasks._tasks.clear()
        tid = tasks.create("x")
        tasks.set_status(tid, "working")
        tasks.set_status(tid, st)
        assert tasks.get(tid).get("finished"), f"«{st}» no sella cuándo terminó"
        assert [r["id"] for r in tasks.recently_finished()] == [tid], f"«{st}» no sale como final reciente"
    tasks._tasks.clear()
