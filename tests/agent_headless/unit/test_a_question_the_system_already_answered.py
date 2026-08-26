"""«¿La paro o sigue?» y «la he parado» llegaron al MISMO prompt (V2-353).

Medido en `search-buy-used-car` ronda 13 (2026-08-26, plató ES), sesión `decce3cc`:

    1512,6 s  🔔 He parado «Busca coches de segunda mano…»: agotó su tiempo   ← la tarea muere
       …      (tres minutos de silencio: el operador no habla)
    1709,1 s  📩 «El proceso «Busca coches…» lleva ya 18 minutos. ¿Quieres que lo pare o que siga?»
    1709,1 s  📩 «He parado «Busca coches…»: agotó su tiempo»

Los dos avisos, sobre la MISMA tarea, en el MISMO instante y en el mismo prompt: uno pregunta si pararla y el
otro dice que ya está parada. El juez fichó [alta] el turno resultante — «narró la parada como si fuera una
decisión propia» — y tenía razón en el síntoma y no en la causa: **un prompt que se contradice no tiene
respuesta obediente** (V2-222, y van cuatro).

POR QUÉ SE JUNTAN, con los números del bucle: la pregunta sale a `WORKER_MAX_SECS` (900 s = 15 min) y la
muerte a `budget + gracia`, que para un worker `web` es 1200 + 90 = 21,5 min. Entre una y otra hay seis
minutos, y ninguna de las dos se entrega al vuelo cuando no hay voz viva: **esperan al siguiente turno del
operador**. Si no habla en esa ventana —y en la ronda medida tardó tres minutos— las dos se drenan juntas.

EL CORTE es que la pregunta sea RETRACTABLE. Una nota que afirma algo sobre estado VIVO puede dejar de ser
verdad antes de entregarse, y quien la hace falsa —el que mata la tarea— es exactamente quien está en
posición de retirarla. No es censura: el que retracta empuja la suya («la he parado») justo después. Lo que se
evita es que lleguen las dos.

Y una llave repetida SUSTITUYE: dos avisos de «lleva N minutos» sobre la misma tarea son el mismo aviso con el
número actualizado, no dos cosas que contar.
"""
import pytest

from voice import brain_notes


@pytest.fixture(autouse=True)
def _buzon_limpio():
    brain_notes.drain()
    yield
    brain_notes.drain()


PREGUNTA = "[SISTEMA] El proceso «Busca coches de segunda mano» lleva ya 18 minutos. ¿Quieres que lo pare?"
PARADA = "[SISTEMA] He parado «Busca coches de segunda mano»: agotó su tiempo."


def test_la_pregunta_se_retracta_cuando_deja_de_tener_sentido():
    """El caso medido, entero."""
    brain_notes.push(PREGUNTA, key="worker-timeout:t3")
    assert brain_notes.retract("worker-timeout:t3") == 1
    brain_notes.push(PARADA)
    assert brain_notes.drain() == [PARADA], "las dos juntas son el prompt que se contradice"


def test_sin_retractar_llegan_las_DOS_que_es_el_defecto():
    """La sensibilidad del de arriba: sin la llamada, el buzón entrega las dos y el modelo elige."""
    brain_notes.push(PREGUNTA, key="worker-timeout:t3")
    brain_notes.push(PARADA)
    assert len(brain_notes.drain()) == 2


def test_una_llave_repetida_SUSTITUYE_no_acumula():
    """«lleva 15 minutos» y «lleva 18 minutos» son el mismo aviso, no dos."""
    brain_notes.push("[SISTEMA] lleva ya 15 minutos. ¿La paro?", key="worker-timeout:t3")
    brain_notes.push("[SISTEMA] lleva ya 18 minutos. ¿La paro?", key="worker-timeout:t3")
    out = brain_notes.drain()
    assert out == ["[SISTEMA] lleva ya 18 minutos. ¿La paro?"]


def test_retractar_solo_toca_SU_tarea():
    """Dos encargos vivos: matar uno no puede callar la pregunta del otro."""
    brain_notes.push("[SISTEMA] el coche lleva 18 min. ¿La paro?", key="worker-timeout:t3")
    brain_notes.push("[SISTEMA] el hotel lleva 16 min. ¿La paro?", key="worker-timeout:t7")
    brain_notes.retract("worker-timeout:t3")
    assert brain_notes.drain() == ["[SISTEMA] el hotel lleva 16 min. ¿La paro?"]


def test_una_nota_SIN_llave_no_se_puede_retractar_por_accidente():
    """La inmensa mayoría de las notas no llevan llave y tienen que quedarse donde están."""
    brain_notes.push("[SISTEMA] el widget ya está construido.")
    brain_notes.push(PREGUNTA, key="worker-timeout:t3")
    brain_notes.retract("worker-timeout:t3")
    assert brain_notes.drain() == ["[SISTEMA] el widget ya está construido."]


def test_retractar_algo_que_no_esta_no_rompe_ni_miente():
    assert brain_notes.retract("worker-timeout:no-existe") == 0
    assert brain_notes.retract("") == 0


def test_el_orden_de_las_notas_se_conserva():
    """El buzón es una cola: la llave no puede reordenar lo que no toca."""
    brain_notes.push("primera")
    brain_notes.push("segunda", key="k")
    brain_notes.push("tercera")
    assert brain_notes.drain() == ["primera", "segunda", "tercera"]


def test_el_bucle_CABLEA_la_llave_en_los_dos_lados():
    """Guarda de cableado sobre la fuente sin comentarios: la retractación sin quien la llame es el arreglo que
    no existe, y este repositorio ya se comió esa exacta forma dos veces (V2-199, V2-340)."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/loop.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    assert "_TIMEOUT_KEY" in src
    assert "_deliver_keyed(" in src, "la pregunta se empuja sin llave: nunca se podrá retractar"
    assert "worker_timeout_running" in src and "_bn.retract(_TIMEOUT_KEY" in src, "nadie retracta al matar"
