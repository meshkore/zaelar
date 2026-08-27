"""Viva, hablando, y 5,5 minutos sin avanzar un solo paso de su plan — invisible (V2-354).

Tercera cara de la misma familia que V2-131 (encallada) y V2-133 (sin paso reportado), y la que faltaba.

Medido en `restaurant-tonight-madrid` (2026-08-27, primera ronda del supervisor, 2/5):

     49,0 s  plan declarado: «4 pasos: Preguntar a la red · Buscar Casa Lucio en TheFork · …»
      …      navegando, leyendo capturas, entrando en casalucio.es y en wa.me
    380,1 s  primer progreso reportado: 1/4

**331 segundos en «0/4, 0%»**, y el bloque de tareas de fondo no sacó NINGUNA cara:

  · `ENCALLADA` mira `silent_s` — «encallado = callado» (V2-131) — y ésta no callaba: emitía cada pocos segundos.
  · `SIN paso reportado aún` (V2-133) solo aplica cuando NO hay plan, y plan sí había.

Y el plan, que existe para ayudar, lo empeoraba: «0/4, 0%» se lee como «acaba de empezar», que es una cifra
tranquilizadora. El juez lo fichó [alta]: «zaelar seguía diciendo "te aviso en cuanto tenga algo"… el usuario
tuvo que insistir TRES veces para obtener algo concreto».

El umbral es más largo que el del silencio a propósito (240 s contra 180): aquí la tarea SÍ trabaja, y un paso
de una gestión web puede costar minutos. Lo que no es normal es que un plan de cuatro pasos siga en cero
pasado ese rato.

Va en `elif`: una tarea CALLADA ya está dicha por la cara de arriba, y sacar las dos es ruido sobre el mismo
hecho. Y el imperativo dice lo que hay que hacer con el dato, no solo el dato — **«sin avanzar» NO es «no ha
empezado»**: está trabajando y no llega, y el operador merece decidir si espera.
"""
import time

import pytest

from nucleo import dispatch
from nucleo.flash import live_blocks as LB


def _cara() -> str:
    """SOLO la parte que describe la tarea, no el imperativo que viene detrás.

    El imperativo NOMBRA las mismas palabras («ENCALLADA o SIN AVANZAR») para que el modelo pueda casarlas, así
    que buscarlas en el bloque entero da verde siempre — el primer intento de este fichero afirmaba justo eso.
    """
    bloque = " ".join(LB.pending_task_lines())
    corte = bloque.find("Si el operador pregunta el estado")
    return bloque[:corte] if corte > 0 else bloque


@pytest.fixture(autouse=True)
def _limpio():
    dispatch._SESSIONS.clear()
    yield
    dispatch._SESSIONS.clear()


def _tarea(*, total=4, done=0, sin_avanzar_s=0, callada_s=0):
    r = dispatch.SessionRecord(task_id="t1", goal="Resérvame mesa esta noche en Madrid", kind="web")
    r.status = "running"
    r.plan = [f"paso {i}" for i in range(total)]
    r.done = done
    ahora = time.time()
    r.started = ahora - max(sin_avanzar_s, callada_s, 1)
    r.last_event_at = ahora - callada_s
    r.last_step_at = ahora - sin_avanzar_s
    dispatch._SESSIONS["t1"] = r
    return r


def test_la_ronda_medida_ahora_SE_DICE():
    """331 s en 0/4: el caso exacto que no salía."""
    _tarea(total=4, done=0, sin_avanzar_s=331)
    linea = _cara()
    assert "SIN AVANZAR" in linea
    assert "5 min sin completar un paso" in linea
    assert "(sigue en 0/4)" in linea, "el operador necesita el número, no solo el adjetivo"


def test_una_tarea_que_AVANZA_no_se_acusa():
    """El lado contrario, y el que importa: un paso completado hace poco no es un atasco."""
    _tarea(total=4, done=2, sin_avanzar_s=30)
    assert "SIN AVANZAR" not in _cara()


def test_recien_arrancada_tampoco():
    _tarea(total=4, done=0, sin_avanzar_s=45)
    assert "SIN AVANZAR" not in _cara()


def test_sin_plan_no_hay_pasos_que_no_avanzar():
    """`SIN paso reportado aún` (V2-133) ya cubre ese caso y dice otra cosa; solaparlos sería contradecirse."""
    r = _tarea(total=0, done=0, sin_avanzar_s=600)
    r.plan = []
    r.phase = ""      # V2-133 solo sale cuando NO hay NADA: ni fase, ni plan, ni progreso, ni nota
    linea = _cara()
    assert "SIN AVANZAR" not in linea
    assert "SIN paso reportado" in linea


def test_una_tarea_CALLADA_dice_lo_suyo_y_no_las_dos():
    """Ruido sobre el mismo hecho: si además lleva minutos muda, ENCALLADA lo explica entero."""
    _tarea(total=4, done=0, sin_avanzar_s=600, callada_s=600)
    linea = _cara()
    assert "ENCALLADA" in linea
    assert "SIN AVANZAR" not in linea


def test_el_reloj_del_avance_arranca_al_DECLARAR_el_plan():
    """Si arrancara al nacer la tarea, un worker que tarda en planificar saldría acusado sin haber prometido
    nada todavía."""
    r = _tarea(total=1, done=0, sin_avanzar_s=0)
    r.started = time.time() - 900
    dispatch.session_plan("t1", "a|b|c|d")
    assert time.time() - r.last_step_at < 2
    assert "SIN AVANZAR" not in _cara()


def test_completar_un_paso_REARMA_el_reloj():
    """Y esto es lo que impide el disco rayado: avanzar borra la acusación."""
    r = _tarea(total=4, done=0, sin_avanzar_s=600)
    assert "SIN AVANZAR" in _cara()
    dispatch.session_progress("t1", "primer paso hecho", done=1)
    assert "SIN AVANZAR" not in _cara()
    assert r.done == 1


def test_reportar_el_MISMO_done_no_rearma_nada():
    """La trampa: un worker que repite `--done 0` cada minuto se estaría auto-absolviendo sin avanzar."""
    _tarea(total=4, done=0, sin_avanzar_s=600)
    dispatch.session_progress("t1", "sigo en ello", done=0)
    assert "SIN AVANZAR" in _cara()


def test_el_imperativo_dice_QUE_hacer_con_el_dato():
    _tarea(total=4, done=0, sin_avanzar_s=331)
    linea = " ".join(LB.pending_task_lines())
    assert "ENCALLADA o SIN AVANZAR" in linea
    assert "no ha empezado" in linea, "el dato solo, sin la lectura, se lee como tranquilizador"
