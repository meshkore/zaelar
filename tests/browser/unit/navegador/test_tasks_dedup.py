"""Dedup de tareas de navegador (control de estado, 2026-07-12).

Invariante: una MISMA búsqueda NO abre un segundo navegador aunque el operador la refine MINUTOS después, mientras
la primera tarea sigue viva. Antes la dedup caducaba a los 45-90 s desde la creación y un refinamiento tardío
spawneaba un navegador gemelo (bug de la sesión de la moto: t1 + t2 en paralelo).
"""
import time

from widgets.navegador import tasks as nt


def _reset():
    with nt._lock:
        nt._tasks.clear()


def test_active_task_dedups_regardless_of_age():
    _reset()
    tid = nt.create("Busca una moto enduro 300 cc 4T por menos de 5000 euros en Wallapop cerca de Soria")
    nt.set_status(tid, "working")
    # Simula que la tarea lleva ACTIVA 5 minutos (300 s) — muy por encima de los viejos 45-90 s.
    with nt._lock:
        nt._tasks[tid]["created"] = time.time() - 300.0
    # Refinamiento tardío del operador ("sube el precio, analízalas una por una") → MISMA búsqueda.
    dup = nt.similar_active("mira en Wallapop motos enduro 250-350 4T y analízalas una por una, sube el precio")
    assert dup == tid, "una tarea ACTIVA debe deduplicar aunque lleve minutos corriendo"


def test_distinct_goal_does_not_merge():
    _reset()
    tid = nt.create("Busca una moto enduro 300 cc 4T en Wallapop")
    nt.set_status(tid, "working")
    dup = nt.similar_active("búscame un piso de alquiler en Madrid en idealista")
    assert dup is None, "dos objetivos distintos (moto vs piso) NO se fusionan"


def test_finished_task_does_not_dedup():
    _reset()
    tid = nt.create("Busca una moto enduro 300 cc 4T en Wallapop")
    nt.set_status(tid, "done")
    dup = nt.similar_active("busca una moto enduro 300 4T en Wallapop")
    assert dup is None, "una tarea TERMINADA no bloquea una búsqueda nueva"


def test_zombie_task_stops_deduping():
    _reset()
    tid = nt.create("Busca una moto enduro 300 cc 4T en Wallapop")
    nt.set_status(tid, "working")
    with nt._lock:  # colgada > 30 min
        nt._tasks[tid]["created"] = time.time() - (nt._ZOMBIE_MAX + 60.0)
    dup = nt.similar_active("busca una moto enduro 300 4T en Wallapop")
    assert dup is None, "una tarea colgada (zombie) no debe bloquear búsquedas nuevas para siempre"


def test_active_summaries_reports_goals():
    _reset()
    tid = nt.create("Busca una moto enduro 300 cc 4T en Wallapop")
    nt.set_status(tid, "working")
    act = nt.active_summaries()
    assert act and act[0][0] == tid and "moto" in act[0][1]


# ── CONTINUIDAD: las aclaraciones modifican la MISMA tarea, no abren un segundo navegador ──────────────────
def test_continuation_active_refines_same_task():
    _reset()
    tid = nt.create("busca una moto para principiantes en Wallapop")
    nt.set_status(tid, "working")
    cont = nt.find_continuation("no, quiero una moto de enduro 300 4T, no eso")
    assert cont == (tid, "working"), "una aclaración sobre la tarea VIVA la continúa (no abre otra)"
    nt.set_goal(tid, "moto enduro 300 4T para principiantes")
    assert nt.get(tid)["goal"] == "moto enduro 300 4T para principiantes"


def test_continuation_finished_task_reopens():
    _reset()
    tid = nt.create("busca una moto para principiantes en Wallapop")
    nt.set_status(tid, "working")
    nt.set_status(tid, "done")            # terminó hace un momento
    cont = nt.find_continuation("las motos no eran de enduro, quiero enduro 300 4T")
    assert cont == (tid, "done"), "un follow-up del mismo tema re-lanza la tarea recién terminada en su tarjeta"


def test_continuation_expired_does_not_reopen():
    _reset()
    tid = nt.create("busca una moto de enduro en Wallapop")
    nt.set_status(tid, "done")
    with nt._lock:                        # terminó hace mucho (> ventana de continuidad)
        nt._tasks[tid]["finished"] = time.time() - (nt._CONTINUATION_MAX + 60.0)
    cont = nt.find_continuation("busca una moto de enduro en Wallapop")
    assert cont is None, "pasada la ventana, es una búsqueda NUEVA"


def test_continuation_prefers_active_over_finished():
    _reset()
    old = nt.create("busca moto enduro en Wallapop"); nt.set_status(old, "done")
    live = nt.create("busca moto enduro en Wallapop"); nt.set_status(live, "working")
    cont = nt.find_continuation("moto enduro 300 4T")
    assert cont == (live, "working"), "si hay una activa del mismo tema, se prefiere refinarla"


def test_continuation_distinct_topic_none():
    _reset()
    tid = nt.create("busca una moto de enduro en Wallapop")
    nt.set_status(tid, "working")
    assert nt.find_continuation("búscame un piso de alquiler en Madrid") is None


# ── explicit trace at creation (V2-108, 2026-08-17) ──────────────────────────────────────────────────────────
# Confirmed against real zaelar.db: every navigation/screenshot/tab_open event for a worker-dispatched web task
# (TaskBrowser._emit → tasks.trace_of(task_id)) carried NO trace, for the task's ENTIRE lifetime — not a
# startup race that settles, since nothing ever writes `trace` again after `create()`. Root cause: `create()`
# read the AMBIENT trace context (`voice.trace.current()`), which is empty inside `nucleo/dispatch.py`'s
# `_prepare_web()` — the worker's own async execution, which never had that scope active — even though the
# caller has the correct id on hand the whole time (`rec.trace_id`, reliably set: the escalation's own tool-call
# events prove it). `create()` now accepts an explicit `trace` that wins over the ambient lookup.
def test_create_with_explicit_trace_does_not_depend_on_ambient_context():
    _reset()
    # No `voice.trace.scope()` active here (plain test context) — this is exactly _prepare_web's situation.
    tid = nt.create("busca hoteles en Sevilla", trace="T366·db44")
    assert nt.trace_of(tid) == "T366·db44", "an explicit trace must win, without depending on ambient context"


def test_create_without_explicit_trace_still_falls_back_to_ambient(monkeypatch):
    _reset()
    monkeypatch.setattr(nt, "_current_trace", lambda: "T999·fallback")
    tid = nt.create("busca hoteles en Sevilla")
    assert nt.trace_of(tid) == "T999·fallback", "without an explicit trace, the old fallback behavior must not break"
