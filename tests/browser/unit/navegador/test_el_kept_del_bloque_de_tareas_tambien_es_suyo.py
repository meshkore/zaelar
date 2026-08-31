"""V2-444 · the same defect, in the SECOND block — and it was the one that actually triggered it.

V2-443 marked `kept` as the worker's assertion on the BROWSER side. The BACKGROUND TASKS block reads the
same field and wrote it just as firmly —«— HAS ALREADY FOUND N candidate(s)»— and also instructed treating it
as a delivery: «if it says … that it HAS ALREADY FOUND candidates, then the task HAS brought that — count it
in this turn».

And it was the one that triggered it. Measured in `best-pediatric-dentists__us` (2026-08-28, 24/7 set): seven
turns (6 through 12) with the prompt saying it had found candidates and **zero rows**, while the sheet had
twenty dentists with names and ratings. The browser side did NOT light up in those seven —four notices in the
entire round, all earlier— so fixing only V2-443 would have left alive the path being measured.

It is the lesson this house has paid for four times: **the failure was not the rule, but having it repeated.**
"""
import pytest

from nucleo import dispatch as D
from nucleo.flash import live_blocks as LB
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as T


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.clear()
    yield
    T._tasks.clear()
    D._SESSIONS.clear()


def _tarea_con_kept(kept):
    tid = T.create("Busca dentistas infantiles", sheet="v444-1")
    T.set_status(tid, "working")
    rec = SessionRecord(task_id="w1", goal="Busca dentistas infantiles", kind="web")
    rec.nav_task, rec.kept, rec.status = tid, kept, "running"
    D._SESSIONS["w1"] = rec
    return tid


def test_el_recuento_se_ATRIBUYE_al_worker():
    _tarea_con_kept(20)
    st = "\n".join(LB.pending_task_lines())
    assert "DICE haber encontrado 20 candidato(s)" in st
    assert "— YA HA ENCONTRADO 20 candidato(s)" not in st


def test_y_deja_de_contarse_como_ENTREGA():
    """The half that changes the turn: the instruction said that the task «HAS brought that» and ordered counting it. With
    twenty rows in the sheet that never traveled to the prompt, that is asking it to name what it does not have."""
    _tarea_con_kept(20)
    st = "\n".join(LB.pending_task_lines())
    assert "es SU cuenta sin comprobar" in st
    assert "NO lo cuentes como entrega ni nombres nada" in st


def test_lo_que_SI_esta_entregado_sigue_ordenandose_contar():
    """Sensitivity: without this, the fix breaks V2-222, which exists because denying a delivery that
    the operator has in front of them is worse than not having made it."""
    _tarea_con_kept(3)
    st = "\n".join(LB.pending_task_lines())
    assert "si dice que algo ya está ENTREGADO, ESCRITO o EN PANTALLA" in st
    assert "la tarea SÍ ha traído eso — cuéntalo en este turno" in st


def test_sin_kept_el_bloque_no_dice_nada_de_candidatos():
    """Zero is not announced: a line that always appears stops being read.

    The task SUMMARY (the one with the em dash in front) is checked, not the entire text: the block
    instruction names the phrase to explain it and is always present — searching for it alone would fail with
    the correct engine, which is a test measuring what it does not think it measures.
    """
    _tarea_con_kept(0)
    st = "\n".join(LB.pending_task_lines())
    assert "— DICE haber encontrado" not in st
