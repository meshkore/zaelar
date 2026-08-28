"""V2-444 · el mismo defecto, en el SEGUNDO bloque — y era el que disparaba de verdad.

V2-443 marcó `kept` como afirmación del worker en la cara del NAVEGADOR. El bloque de TAREAS DE FONDO lee el
mismo campo y lo escribía igual de firme —«— YA HA ENCONTRADO N candidato(s)»— y además ordenaba tratarlo
como entrega: «si dice … que YA HA ENCONTRADO candidatos, entonces la tarea SÍ ha traído eso — cuéntalo en
este turno».

Y es el que disparaba. Medido en `best-pediatric-dentists__us` (2026-08-28, plató 24/7): siete turnos (6 al
12) con el prompt diciendo que había encontrado candidatos y **cero filas**, con la hoja teniendo veinte
dentistas con nombre y valoración. La cara del navegador NO se encendió en esos siete —cuatro avisos en toda
la ronda, todos anteriores— así que arreglar solo V2-443 habría dejado vivo el camino que se estaba midiendo.

Es la lección que esta casa lleva pagada cuatro veces: **el fallo no fue la regla, fue tenerla repetida.**
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
    """La mitad que cambia el turno: la orden decía que la tarea «SÍ ha traído eso» y mandaba contarlo. Con
    veinte filas en la hoja que nunca viajaron al prompt, eso es pedir que nombre lo que no tiene."""
    _tarea_con_kept(20)
    st = "\n".join(LB.pending_task_lines())
    assert "es SU cuenta sin comprobar" in st
    assert "NO lo cuentes como entrega ni nombres nada" in st


def test_lo_que_SI_esta_entregado_sigue_ordenandose_contar():
    """Sensibilidad: sin esto el arreglo se lleva por delante V2-222, que existe porque negar una entrega que
    el operador tiene delante es peor que no haberla hecho."""
    _tarea_con_kept(3)
    st = "\n".join(LB.pending_task_lines())
    assert "si dice que algo ya está ENTREGADO, ESCRITO o EN PANTALLA" in st
    assert "la tarea SÍ ha traído eso — cuéntalo en este turno" in st


def test_sin_kept_el_bloque_no_dice_nada_de_candidatos():
    """Un cero no se anuncia: una línea que sale siempre deja de leerse.

    Se comprueba el RESUMEN de la tarea (el que lleva el guion largo delante), no el texto entero: la
    instrucción del bloque nombra la frase para explicarla y está siempre — buscarla a secas daría rojo con
    el motor correcto, que es un test midiendo lo que no cree medir.
    """
    _tarea_con_kept(0)
    st = "\n".join(LB.pending_task_lines())
    assert "— DICE haber encontrado" not in st
