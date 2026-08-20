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
    yield
    dispatch._SESSIONS.clear()


def _session(status: str, *, ok: bool = True, summary: str = "", goal: str = "Buscar un monitor") -> None:
    r = dispatch.SessionRecord(task_id="w1", goal=goal, kind="generic")
    r.status, r.ok, r.result_summary = status, ok, summary
    dispatch._SESSIONS["w1"] = r


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
    _session("running")
    state = _state()
    assert "YA ACABADAS" not in state
    assert "TAREAS DE FONDO EN CURSO" in state


def test_and_an_old_ending_is_not_this_conversation():
    import time as _t

    _session("done")
    dispatch._SESSIONS["w1"].last_event_at = _t.time() - (dispatch.JUST_ENDED_S + 60)
    assert dispatch.recently_ended_sessions() == []


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
