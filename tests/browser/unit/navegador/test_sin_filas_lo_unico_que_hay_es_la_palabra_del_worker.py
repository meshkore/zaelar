"""V2-443 · sin filas, la cara afirmaba como HECHO lo que solo dice el worker.

`_found_candidates` tiene dos fuentes: las filas de la hoja (un hecho, las escribe `intake.push`) y `kept`,
la cuenta que el propio worker escribe con `hbnote considered --kept N`. Sin filas solo queda la segunda —una
AFIRMACIÓN suya, no algo comprobado— y el bloque la renderizaba como «YA HA ENCONTRADO algo», prohibiéndole
además al turno decir lo contrario: «NO digas que sigue sin resultados … eso es falso».

Medido en `find-theatre-tickets__us` (2026-08-28, plató 24/7): la cara disparó **once veces** con
`worker_outcome.found: []`, cero extracciones con filas y la hoja vacía en todas partes (censo de V2-440: los
once avisos, DESFASE). El worker dijo tener finalistas y no había ninguno. Le poníamos al turno una
afirmación falsa delante y le prohibíamos la verdadera, así que la única salida que le dejábamos era decirle
al operador que ya estaba sacando cosas — y luego eso se puntúa como que el agente promete lo que no tiene.

La prohibición era el error, no un exceso: para el operador «todavía no ha llegado nada» es CIERTO, y es lo
que necesita para decidir si espera o cambia de sitio. Es la familia de V2-358 («un paso que el worker
escribe sobre la pantalla es una afirmación suya») y de V2-249 (la píldora auto-avalada): no se tira, se
MARCA.
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
    # …y no la afirmación en firme, que es la que el turno repetía al operador
    assert "YA HA ENCONTRADO algo: no está bloqueada ni esperando, pero" not in state


def test_sin_filas_YA_NO_se_le_prohibe_decir_que_no_ha_llegado_nada():
    """La mitad que de verdad cambia el turno. Con la prohibición delante, la única salida que le quedaba era
    afirmar que ya estaba sacando cosas — con la hoja vacía y el worker sin haber encontrado nada."""
    tid = T.create("Busca entradas de teatro", sheet="v443-2")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "NO digas que sigue «sin resultados»" not in state
    assert "aún no ha llegado nada" in state


def test_pero_lo_que_SI_seria_falso_se_sigue_prohibiendo():
    """Sin esta mitad el arreglo abre la puerta a lo contrario: inventar nombres o decir que están en
    pantalla, que es lo que V2-278 cerró y costó un [alta] por afirmación sin respaldo."""
    tid = T.create("Busca entradas de teatro", sheet="v443-3")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "NO te inventes nombres" in state
    assert "ni que están en pantalla" in state


def test_la_tarea_sigue_diciendose_VIVA_para_no_reabrir_V2_152():
    """«No ha llegado nada» no puede leerse como «está parada»: eso empuja a relanzar una tarea que va bien,
    que es el daño real que V2-152 midió."""
    tid = T.create("Busca entradas de teatro", sheet="v443-4")
    T.set_status(tid, "working")
    _worker_que_dice_tener(tid, 4)
    state = "\n".join(LB.navegador_lines())
    assert "no está bloqueada ni esperando" in state and "sigue trabajando" in state


def test_CON_filas_la_cara_no_se_toca_porque_ahi_SI_es_un_hecho():
    """La hoja respalda la afirmación: ahí «ya ha encontrado» es verdad y la orden de contarlo con nombre y
    precio es cumplible. Debilitarla también sería un defecto — el de V2-330 por el otro lado."""
    tid = T.create("Busca entradas de teatro", sheet="v443-5")
    T.set_status(tid, "working")
    SHEET.apply_action("present", {"sheet": "v443-5", "title": "Resultados",
                                   "items": [{"title": "The Lion King · Minskoff", "price": "120 $"}]})
    state = "\n".join(LB.navegador_lines())
    assert "YA HA ENCONTRADO algo: no está bloqueada ni esperando. CUÉNTALE" in state
    assert "DICE QUE YA TIENE CANDIDATOS" not in state
