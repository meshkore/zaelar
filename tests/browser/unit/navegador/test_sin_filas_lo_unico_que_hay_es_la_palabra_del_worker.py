"""V2-443 · with no rows, the face stated as FACT what the worker merely says.

`_found_candidates` has two sources: the sheet's rows (a fact, written by `intake.push`) and `kept`,
the count that the worker itself writes with `hbnote considered --kept N`. With no rows, only the second remains—a
CLAIM of its own, not something verified—and the block rendered it as «YA HA ENCONTRADO algo», also forbidding
the turn from saying the opposite: «NO digas que sigue sin resultados … eso es falso».

Measured on `find-theatre-tickets__us` (2026-08-28, 24/7 set): the face fired **eleven times** with
`worker_outcome.found: []`, zero extractions with rows, and the sheet empty everywhere (V2-440 census: the
eleven alerts, MISMATCH). The worker said it had finalists, and there were none. We put a
false assertion in front of the turn and forbade the true one, so the only output we left it was to tell
the operator that it was already pulling things out—and then that gets scored as the agent promising what it does not have.

The prohibition was the error, not an excess: for the operator, «todavía no ha llegado nada» is TRUE, and it is what
they need to decide whether to wait or move elsewhere. It belongs to the family of V2-358 («un paso que el worker
escribe sobre la pantalla es una afirmación suya») and V2-249 (the self-validated pill): it is not thrown away, it is
MARKED.
"""
import pytest

from nucleo import dispatch as D
from nucleo.flash import live_blocks as LB
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.clear()
    yield
    T._tasks.clear()
    D._SESSIONS.clear()


def _worker_que_dice_tener(tid, kept):
    rec = SessionRecord(task_id="w1", goal="Busca entradas", kind="web")
    rec.nav_task, rec.kept, rec.status = tid, kept, "running"
    D._SESSIONS["w1"] = rec


def test_sin_filas_la_cara_dice_que_lo_DICE_el_worker_y_no_que_sea_un_hecho():
    tid = T.create("Busca entradas de teatro", sheet="v443-1")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "DICE QUE YA TIENE CANDIDATOS" in state
    assert "es SU cuenta, no la hemos comprobado" in state
    # …and not the firm assertion, which is what the turn was repeating to the operator
    assert "YA HA ENCONTRADO algo: no está bloqueada ni esperando, pero" not in state


def test_sin_filas_YA_NO_se_le_prohibe_decir_que_no_ha_llegado_nada():
    """The half that actually changes the turn. With the prohibition in front of it, the only output it had left was
    to claim that it was already pulling things out—with the sheet empty and the worker having found nothing."""
    tid = T.create("Busca entradas de teatro", sheet="v443-2")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "NO digas que sigue «sin resultados»" not in state
    assert "aún no ha llegado nada" in state


def test_pero_lo_que_SI_seria_falso_se_sigue_prohibiendo():
    """Without this half, the fix opens the door to the opposite: inventing names or saying they are on the
    screen, which is what V2-278 closed off and cost a [high] for an unsupported assertion."""
    tid = T.create("Busca entradas de teatro", sheet="v443-3")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "NO te inventes nombres" in state
    assert "ni que están en pantalla" in state


def test_la_tarea_sigue_diciendose_VIVA_para_no_reabrir_V2_152():
    """«No ha llegado nada» cannot be read as «está parada»: that pushes toward relaunching a task that is doing well,
    which is the actual harm V2-152 measured."""
    tid = T.create("Busca entradas de teatro", sheet="v443-4")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "no está bloqueada ni esperando" in state and "sigue trabajando" in state


def test_CON_filas_la_cara_no_se_toca_porque_ahi_SI_es_un_hecho():
    """The sheet supports the assertion: there, «ya ha encontrado» is true and the instruction to report it with a name and
    price is actionable. Weakening it too would be a defect—the one V2-330 identified from the other side."""
    tid = T.create("Busca entradas de teatro", sheet="v443-5")
    T.set_status(tid, "working")
    SHEET.apply_action("present", {"sheet": "v443-5", "title": "Resultados",
                                   "items": [{"title": "The Lion King · Minskoff", "price": "120 $"}]})
    state = "\n".join(LB.navegador_lines())
    assert "YA HA ENCONTRADO algo: no está bloqueada ni esperando. CUÉNTALE" in state
    assert "DICE QUE YA TIENE CANDIDATOS" not in state
