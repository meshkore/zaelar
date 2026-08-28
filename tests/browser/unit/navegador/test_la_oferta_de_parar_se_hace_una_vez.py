"""V2-454 · la oferta de parar una tarea atascada se repetía turno tras turno.

El bloque decía «si una tarea sale ENCALLADA o SIN AVANZAR, dilo con esas letras **la primera vez** que salga
a colación y ofrece pararla», y el modelo **no puede saber si es la primera**: eso es un hecho NUESTRO, la
misma lección que V2-224 aprendió con el aviso de muerte. Sin contarlo, la oferta se renderiza en TODOS los
turnos que la tarea siga atascada.

Medido sobre las 334 rondas guardadas: **49 (14 %) repiten la oferta de parar dos o más veces**, y diez de
las últimas quince del 2026-08-28. El daño no es la redundancia — **el operador YA CONTESTÓ**: en
`search-buy-used-car` (10:57) dijo «párale y prueba de nuevo, o miramos por otro sitio, tú decides» y el
turno siguiente volvió a plantear la misma disyuntiva; el juez lo puso de bloqueador [alta].

Y la regla que gobierna la redacción es la de V2-224: **callar la repetición no es callar el estado.**
"""
import pytest

from nucleo import dispatch as D
from nucleo import turn_marks
from nucleo.flash import task_block as TB
from nucleo.workers.session import SessionRecord


@pytest.fixture(autouse=True)
def _clean():
    D._SESSIONS.clear()
    turn_marks._STALL_OFFERED.clear()
    yield
    D._SESSIONS.clear()
    turn_marks._STALL_OFFERED.clear()


def _atascada(tid="w1"):
    import time
    rec = SessionRecord(task_id=tid, goal="busca un fontanero", kind="web")
    rec.status = "running"
    rec.started = time.time() - 900
    rec.last_event_at = time.time() - 900          # ENCALLADA: sin señal
    D._SESSIONS[tid] = rec
    return rec


def test_la_PRIMERA_vez_se_ofrece_parar():
    _atascada()
    st = "\n".join(TB.pending_task_lines())
    assert "ENCALLADA" in st
    assert "YA le ofreciste" not in st


def test_la_SEGUNDA_vez_se_dice_que_NO_lo_vuelva_a_preguntar():
    _atascada()
    TB.pending_task_lines()                        # turno 1: se la lleva delante
    st = "\n".join(TB.pending_task_lines())        # turno 2
    assert "YA le ofreciste pararla" in st and "NO se lo vuelvas a preguntar" in st


def test_pero_el_HECHO_se_sigue_diciendo():
    """La regla de V2-224: callar la repetición NO es callar el estado. Si al quitar la oferta se quitara el
    hecho, el turno volvería a «sigue en marcha» — que es el silencio que V2-131 cerró."""
    _atascada()
    TB.pending_task_lines()
    st = "\n".join(TB.pending_task_lines())
    assert "ENCALLADA" in st and "SIN DAR NINGUNA SEÑAL" in st


def test_una_tarea_SANA_no_marca_nada():
    """Sensibilidad: si se marcara siempre, la primera tarea que SÍ se atasque nacería ya «ofrecida» y nadie
    le ofrecería nunca parar nada."""
    import time
    rec = SessionRecord(task_id="w2", goal="algo", kind="web")
    rec.status, rec.started, rec.last_event_at = "running", time.time(), time.time()
    D._SESSIONS["w2"] = rec
    TB.pending_task_lines()
    assert D.stall_offered("w2") == 0


def test_cada_tarea_lleva_su_propia_cuenta():
    """Dos encargos atascados son dos ofertas: compartir la marca dejaría al segundo sin que nadie le
    ofreciera nada."""
    _atascada("w1"); _atascada("w3")
    TB.pending_task_lines()
    assert D.stall_offered("w1") == 1 and D.stall_offered("w3") == 1


def test_el_bloque_le_DICE_al_modelo_que_no_repita_la_pregunta():
    """La instrucción, no solo la marca: sin la frase, el modelo tiene el hecho y no sabe qué hacer con él."""
    _atascada()
    st = "\n".join(TB.pending_task_lines())
    assert "la pregunta NO se \nrepite" in st or "la pregunta NO se repite" in st.replace("\n", "")
