"""A TAB survives the worker that opened it, and its sheet was resolved through the registry of live sessions (V2-281).

Measured in `search-secondhand-monitor__es` (2026-08-24 01:47), the run that passed:

    by task: results: 24 row(s) «Resultados» · results::9fc24a-1: 12 row(s) «Busca un monitor…»

ONE task, and its findings split between two boxes — with the MAJORITY in the BARE sheet, which since V2-259 belongs
to no one. And that orphaned box is also the «GHOST CARD» that the canvas has been reporting for several runs.

The cause: `act_api._sheet_of` resolved through `dispatch.sheet_for_nav_task`, which walks `_SESSIONS` — the
registry of LIVE sessions. But a tab outlives its worker: the record is removed in `_run_session`'s `finally`,
and a provider handoff (V2-238) opens a new worker. Thus every finding that arrived after that death resolved
to "" and fell into the default sheet.

It is the SAME pattern as V2-108 with the `trace`: a fact the caller has when creating the tab and that the
registry can no longer answer later. Same remedy: seal it at birth.
"""
import pytest

from widgets.navegador import act_api
from widgets.navegador import tasks as T


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    yield
    T._tasks.clear()


def test_la_pestana_guarda_la_hoja_de_su_encargo():
    tid = T.create("Busca un monitor de segunda mano", sheet="9fc24a-1")
    assert T.get(tid)["sheet"] == "9fc24a-1"
    assert act_api._sheet_of(tid) == "9fc24a-1"


def test_y_la_conserva_cuando_su_worker_YA_NO_ESTA():
    """The measured case: the record died (handoff) and the finding arrives afterward."""
    from nucleo import dispatch as D
    tid = T.create("Busca un monitor de segunda mano", sheet="9fc24a-1")
    D._SESSIONS.clear()                       # the worker died and `_run_session` removed its record
    assert D.sheet_for_nav_task(tid) == "", "el registro de vivos ya no puede contestar — ése era el agujero"
    assert act_api._sheet_of(tid) == "9fc24a-1", "el hallazgo tardío vuelve a caer en la hoja de nadie"


def test_una_pestana_SIN_encargo_sigue_entregando_en_la_hoja_de_siempre():
    """The operator driving the browser manually: there is no task, so there is no instance. That is correct,
    and turning it into an invented ID would be worse than the defect."""
    assert act_api._sheet_of(T.create("el operador abre una web")) == ""


def test_el_registro_de_sesiones_sigue_siendo_el_RESPALDO():
    """A tab created BEFORE this change has no seal, and while its worker is alive the registry does know.

    Without this half, «fixing» resolution would break it for everything that was already open.
    """
    from nucleo import dispatch as D
    from nucleo import surfaces
    from nucleo.workers.session import SessionRecord
    tid = T.create("Busca un monitor")                    # without a seal, like the old ones
    rec = SessionRecord(task_id="w9", goal="Busca un monitor", kind="web")
    surfaces.set_once(rec, "lista")
    rec.status, rec.nav_task, rec.sheet = "running", tid, "viejo-1"
    D._SESSIONS.clear()
    D._SESSIONS["w9"] = rec
    try:
        assert act_api._sheet_of(tid) == "viejo-1"
    finally:
        D._SESSIONS.clear()


def test_el_sello_lo_PONE_quien_prepara_la_pestana():
    """The half that no measurement of the module sees: that `_prepare_web` actually passes it along.

    It is the lesson of V2-199 — a fix whose data is never written passes its tests and does nothing.
    """
    import inspect

    from nucleo import dispatch as D
    src = inspect.getsource(D._prepare_web)
    assert "sheet=sheet_of(rec)" in src, "la pestaña vuelve a nacer sin saber de qué encargo es"
