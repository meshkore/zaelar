"""Three workers resuming the SAME CLI session, and all three dying at 400 ms (V2-237).

Measured by the harness on 2026-08-21 in `best-plumber-same-day` (1/5, mechanism 2, **zero rows extracted**), with
a correlation that leaves no room for doubt:

    worker 3  «REANUDA sesión nativa c5ad1d9e-ad0…»  → ERROR a los 371 ms
    worker 4  «REANUDA sesión nativa c5ad1d9e-ad0…»  → ERROR a los 401 ms   ← LA MISMA
    worker 6  «REANUDA sesión nativa c5ad1d9e-ad0…»  → ERROR a los 374 ms   ← LA MISMA
    workers 2 y 5, sesión NUEVA, sin reanudar        → vivos

**3 out of 3 versus 0 out of 3.** Their entire trace consists of five events in 400 ms: alive → widget show → task start
(«Buscando en la web…») → task end. A web search does not last 400 ms: they died during startup, before doing
anything, and the case ended up without a single extraction.

The cause: `_find_resume` READ the entry without consuming it, so every escalation of the same request—including
those triggered by V2-049's auto-resume—received the SAME `native_sid`. A CLI session cannot be resumed twice
at the same time.

Consuming it is safe because the lifecycle already returns it: when closing an incomplete web operation, `_run_session`
rewrites the entry with the current `native_sid`. And if the worker dies before reaching that point, the resumption is
lost and the next task starts from scratch—strictly better than dying in 400 ms.
"""
import time

import pytest

from nucleo import dispatch
from nucleo.workers import resume as _wres

PETICION = "busca un fontanero que pueda venir hoy a arreglar una fuga en Madrid"
OTRA = "reserva mesa para dos esta noche en un restaurante de Sevilla"


@pytest.fixture(autouse=True)
def _registro_aislado(monkeypatch):
    # V2-342: the subsystem lives in `nucleo/workers/resume.py`; patch it THERE, where the functions
    # read their globals—patching dispatch's alias would leave the real dict intact and the test would measure nothing.
    from nucleo.workers import resume as _wres
    monkeypatch.setattr(_wres, "_WEB_RESUME", {}, raising=False)
    monkeypatch.setattr(_wres, "_resume_persist", lambda: None, raising=False)
    yield


def _sembrar(req=PETICION, sid="c5ad1d9e-ad0"):
    _wres._WEB_RESUME[dispatch._goal_key(req)] = {
        "nav_task": "t9", "native_sid": sid, "ts": time.time(), "count": 1, "goal": req[:200]}


# ── the measured case ─────────────────────────────────────────────────────────────────────────────────────────

def test_solo_el_PRIMERO_se_lleva_la_sesion_nativa():
    _sembrar()
    primero = dispatch._find_resume(PETICION, take=True)
    segundo = dispatch._find_resume(PETICION, take=True)
    tercero = dispatch._find_resume(PETICION, take=True)
    assert primero and primero["native_sid"] == "c5ad1d9e-ad0"
    assert segundo is None, "el segundo worker reanudaba la misma sesión del CLI y moría en el arranque"
    assert tercero is None


def test_sin_reanudacion_el_encargo_ARRANCA_de_cero():
    """What the two survivors do: use their own session. Losing continuity is worse than losing the worker,
    but much better than losing BOTH the worker and continuity."""
    _sembrar()
    dispatch._find_resume(PETICION, take=True)
    assert dispatch._find_resume(PETICION, take=True) is None


# ── the other direction: consuming cannot break V2-049 continuity ────────────────────────────────────────────

def test_la_entrada_VUELVE_al_cerrar_una_gestion_incompleta():
    """WIRING GUARD: without rewriting on close, consuming the entry would turn auto-resume into a single
    attempt and V2-049's web continuity would die silently. The property crosses a seam from V2-342: rewriting
    lives in `_leave_resume` and `_run_session` has to CALL it—the two halves are asserted because each one alone
    is a loose wire."""
    import inspect
    assert "_leave_resume(" in inspect.getsource(dispatch._run_session)
    assert "_WEB_RESUME[gk] = _resume_entry(" in inspect.getsource(dispatch._leave_resume)


def test_leerla_SIN_tomarla_sigue_siendo_posible():
    """`take` is explicit by design: anyone who only wants to check whether something can be resumed must not take it."""
    _sembrar()
    assert dispatch._find_resume(PETICION) is not None
    assert dispatch._find_resume(PETICION) is not None, "una lectura no puede consumir"


def test_una_peticion_DISTINTA_no_se_lleva_la_reanudacion_de_otra():
    _sembrar()
    assert dispatch._find_resume(OTRA, take=True) is None
    assert dispatch._find_resume(PETICION, take=True) is not None


def test_una_entrada_caducada_no_se_entrega():
    _wres._WEB_RESUME[dispatch._goal_key(PETICION)] = {
        "nav_task": "t9", "native_sid": "viejo", "ts": time.time() - dispatch._RESUME_TTL - 10, "count": 1}
    assert dispatch._find_resume(PETICION, take=True) is None


def test_el_listener_la_TOMA_y_no_solo_la_lee():
    """The defect was not the predicate but its caller. Without `take=True` in `run_listener`, this remains exactly
    as broken and the tests above pass—the lesson of V2-199."""
    import inspect
    src = inspect.getsource(dispatch.run_listener)
    assert "_find_resume(request, take=True)" in src


# ── the other finding from the same round: an unexplained ending ─────────────────────────────────────────────
# “A worker that dies does not leave even one event saying why”: `task|end` arrived with `text:""` and the model,
# and nothing else. The only error events in the round belonged to the worker that did NOT die, so the cause of the
# four deaths could only be seen by cross-referencing the engine log by `span=worker:N`. An unexplained ending reads
# the same as a normal ending.

def test_la_fila_del_final_LLEVA_el_motivo_y_el_estado():
    """SOURCE GUARD: construction lives inside `_finish`, which needs a live backend to reach that point.
    What can be checked without one is that the reason and status are put into the row—and that is exactly what
    a regression would undo without failing noisily, once again leaving `text:""` for a dead worker."""
    import inspect

    from nucleo.workers import session as _s
    src = inspect.getsource(_s.WorkerSession._finish)
    assert 'extra["status"] = str(rec.status or "")' in src
    assert "if not rec.ok:" in src and "rec.result_summary" in src


# ── V2-239: consuming it is not enough if the death path rebuilds it ─────────────────────────────────────────
# The harness measured the fix above AT 05dd79f, with the worktree pinned and `n_dirty=0`, and it did NOT close: session
# `0364d544-505` → workers 3 and 4, dead 2/2, lifetimes 380 and 420 ms. `take=True` consumed correctly. What failed
# was the other end of the cycle: on close, the entry was rewritten with
#
#     "native_sid": rec.native_sid or str((resume or {}).get("native_sid") or "")
#
# meaning that a worker dying BEFORE the CLI announced its session returned the INHERITED id to the entry—
# the same one that had just killed it—and the next worker took it. An id that kills must not be rebuilt.


class _Rec:
    def __init__(self, native_sid=""):
        self.native_sid = native_sid


def test_un_worker_que_MURIO_sin_sesion_propia_no_devuelve_el_id_heredado():
    ent = dispatch._resume_entry(_Rec(""), nav_tid="t9", resume={"native_sid": "0364d544-505", "nav_task": "t9"},
                                 req=PETICION, key="k1", brief=False, prev_count=1)
    assert ent["native_sid"] == "", "el id que acababa de matar al worker volvía a la entrada"


def test_una_reanudacion_que_PRENDE_conserva_su_id():
    """The other direction, and the one that supports V2-049: Claude Code's `system/init` arrives the same in a clean
    startup as in a `--resume`, so a live resumption DOES leave `native_sid`. Without this case, the fix above could
    be satisfied by always deleting the id—and that silently kills web continuity."""
    ent = dispatch._resume_entry(_Rec("nuevo-sid"), nav_tid="t9", resume={"native_sid": "viejo"},
                                 req=PETICION, key="k1", brief=False, prev_count=1)
    assert ent["native_sid"] == "nuevo-sid"


def test_la_PESTAÑA_del_navegador_si_conserva_su_respaldo():
    """The browser tab is another resource: it survives the worker that opened it and is not what was killing anyone."""
    ent = dispatch._resume_entry(_Rec(""), nav_tid="", resume={"nav_task": "t9", "native_sid": "x"},
                                 req=PETICION, key="k1", brief=False, prev_count=1)
    assert ent["nav_task"] == "t9" and ent["native_sid"] == ""


def test_el_contador_de_intentos_SIGUE_subiendo():
    """The `_RESUME_CAP` cap is what stops a task that is not progressing: if losing the id also lost the count,
    a broken case would retry forever."""
    ent = dispatch._resume_entry(_Rec(""), nav_tid="t9", resume={"native_sid": "x"},
                                 req=PETICION, key="k1", brief=False, prev_count=3)
    assert ent["count"] == 4


def test_el_criterio_ACORDADO_viaja_igual():
    ent = dispatch._resume_entry(_Rec(""), nav_tid="t9", resume={"brief_task": "b7"},
                                 req=PETICION, key="k1", brief=False, prev_count=0)
    assert ent["brief_task"] == "b7"
    ent2 = dispatch._resume_entry(_Rec(""), nav_tid="t9", resume={}, req=PETICION, key="k9",
                                  brief=True, prev_count=0)
    assert ent2["brief_task"] == "k9"
