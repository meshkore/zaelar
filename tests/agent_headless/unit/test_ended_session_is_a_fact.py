"""Una SESIÓN de worker que acaba también es un hecho (V2-198).

V2-150 cerró esto para las tareas de NAVEGADOR: «una tarea que TERMINA desaparecía del estado, así que no
quedaba ningún hecho diciendo que había acabado, y menos aún que había acabado vacía… se le había quitado de
delante lo único que podía contradecirle».

El mismo hueco existía un nivel por encima y **es peor**: una tarea de navegador solo existe con `kind=web`,
mientras que TODA escalada abre una sesión de worker. Los casos que se resuelven por BÚSQUEDA
(`cheapest-monitor`) o por MEMORIA (`remember-and-remind-deadline`) no tienen tarea de navegador en absoluto,
así que para ellos el arreglo de V2-150 nunca llegó a aplicarse — y son justo los que el arnés viene midiendo
como «el usuario esperando sin feedback» y «espera infinita».

Además había CUATRO filtros escribiendo `("queued", "running")` a mano, que es la misma forma que V2-197
cerró en el registro del navegador: dos listas que hay que mantener sincronizadas son dos listas que no lo
van a estar.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from nucleo import dispatch

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _clean():
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()
    dispatch._ENDED_SESSIONS.clear()


def _live_session(status: str = "running", goal: str = "Buscar un monitor"):
    r = dispatch.SessionRecord(task_id="w1", goal=goal, kind="generic")
    r.status = status
    dispatch._SESSIONS["w1"] = r
    return r


def _session(status: str, *, ok: bool = True, summary: str = "", goal: str = "Buscar un monitor") -> None:
    """Una sesión que ACABÓ, por el MISMO camino que la producción.

    V2-199 — la primera versión de este helper metía el registro en `_SESSIONS` y lo dejaba ahí. Pasaba, y no
    probaba nada: `_run_session` **saca el registro en su `finally`**, así que en un dispatch de verdad no
    quedaba nada que leer y `recently_ended_sessions()` devolvía cero. Lo descubrió una escalada real, no la
    suite. Ahora se llama al mismo `_remember_ended()` que llama el `finally`, y hay un test que exige que ese
    sitio lo siga llamando."""
    r = _live_session(status, goal)
    r.ok, r.result_summary = ok, summary
    dispatch._remember_ended(r)
    dispatch._SESSIONS.pop("w1", None)          # como hace `_run_session`


def _state() -> str:
    from nucleo.flash import prompt as _p
    return _p.live_state()


def test_a_finished_session_does_not_vanish():
    _session("done", summary="3 monitores encontrados")
    assert dispatch.pending_summaries() == []            # ya no está viva…
    assert [r["id"] for r in dispatch.recently_ended_sessions()] == ["w1"]   # …pero SÍ es un final
    state = _state()
    assert "TAREAS DE FONDO — YA ACABADAS" in state
    assert "3 monitores encontrados" in state            # y con lo que trajo, que es lo que el operador quiere


@pytest.mark.parametrize("status,ok,marca", [("done", True, "TERMINÓ"),
                                             ("cancelled", True, "se PARÓ (cancelada)"),
                                             ("error", False, "FALLÓ")])
def test_and_each_ending_sounds_like_what_it_was(status, ok, marca):
    """Un final que suena igual que otro distinto no sirve: «terminó» invita a pedir el resultado, «se paró» a
    preguntar si se retoma, y «falló» a intentar otra cosa."""
    _session(status, ok=ok)
    assert marca in _state()


def test_but_a_LIVE_session_is_not_announced_as_ended():
    """La sensibilidad: sin esto, «di cómo acabó» y «di siempre que acabó» pasan igual."""
    _live_session("running")
    state = _state()
    assert "YA ACABADAS" not in state
    assert "TAREAS DE FONDO EN CURSO" in state


def test_and_an_old_ending_is_not_this_conversation():
    import time as _t

    _session("done")
    dispatch._ENDED_SESSIONS["w1"]["at"] = _t.time() - (dispatch.JUST_ENDED_S + 60)
    assert dispatch.recently_ended_sessions() == []


def test_the_REAL_path_records_the_ending_before_dropping_the_record():
    """El test que faltaba, y el único que habría cazado el fallo: `_run_session` TIRA el registro en su
    `finally`, así que leer `_SESSIONS` para los finales no encuentra nunca nada. Lo descubrió una escalada
    real; esto lo fija sin tener que correr una."""
    import inspect

    src = inspect.getsource(dispatch._run_session)
    # El ÚLTIMO pop es el del `finally`, por donde sale toda sesión que llega a ejecutarse. Los otros dos son
    # el confirm-gate —que tiene su propia línea de estado (V2-126/V2-190) y anunciarlo además como «TERMINÓ»
    # sería contarlo dos veces y mal— y la cancelación en cola, que sí recuerda.
    i = src.rindex("_SESSIONS.pop(key, None)")
    antes = src[:i]
    assert "_remember_ended(rec)" in antes, (
        "`_run_session` tira el registro sin recordar cómo acabó: `recently_ended_sessions()` no verá nada y "
        "el turno volverá a quedarse con su memoria de haber arrancado la tarea.")


def test_and_the_snapshot_does_not_hold_the_worker_handles():
    """Se guarda un dict ligero y no el `SessionRecord`: ese objeto lleva los handles del worker, y mantenerlo
    vivo cinco minutos más allá del final los mantendría vivos también."""
    _session("done", summary="algo")
    row = dispatch._ENDED_SESSIONS["w1"]
    assert isinstance(row, dict)
    assert set(row) == {"id", "goal", "status", "ok", "summary", "at"}


# ── la enumeración, una sola vez (misma lección que V2-197) ───────────────────────────────────────────────
_SET = re.compile(r"\.status\s*=\s*[\"']([a-z_]+)[\"']")


def test_the_two_sets_do_not_overlap():
    assert not (dispatch.LIVE_SESSION_STATES & dispatch.ENDED_SESSION_STATES)


def test_every_session_status_the_code_writes_is_classified():
    found: set[str] = set()
    for d in ("nucleo", "server", "voice"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for py in base.rglob("*.py"):
            try:
                found |= set(_SET.findall(py.read_text(encoding="utf-8", errors="replace")))
            except Exception:
                continue
    known = dispatch.LIVE_SESSION_STATES | dispatch.ENDED_SESSION_STATES
    # `.status = "x"` es un patrón ancho: solo se exigen los que declara el propio SessionRecord.
    declared = {"queued", "running", "done", "error", "cancelled"}
    unclassified = sorted((found & declared) - known)
    assert not unclassified, (
        f"estados de SESIÓN sin clasificar: {unclassified}. Una sesión en ese estado no aparece en el estado "
        "vivo —ni viva ni acabada— y el turno se queda con su memoria de haberla arrancado.")


def test_and_nobody_enumerates_them_by_hand_anymore():
    """Cuatro filtros escribían `("queued", "running")` cada uno por su cuenta. Es la forma exacta que dejó a
    `cancelled` fuera en el registro del navegador (V2-196)."""
    src = (ROOT / "nucleo" / "dispatch.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
    code = code.replace('LIVE_SESSION_STATES = frozenset({"queued", "running"})', "")
    assert '"queued", "running"' not in code
