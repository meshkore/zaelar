"""Un RESET rebobinaba el contador y el sello no, así que la búsqueda siguiente heredaba —y borraba— la caja
de la anterior (V2-283).

Medido en la tanda del 2026-08-24 03:02: CUATRO casos en un solo proceso de plató, y los cuatro encargos
cayeron en `results--c2567e-1`. La misma caja, estrenada con `begin_task(fresh=True)` cada vez, así que cada
caso borró los hallazgos del anterior. En el informe del caso del MONITOR salieron seis títulos de GUITARRA y
en el de la GUITARRA, títulos de BICICLETA.

Es LITERALMENTE lo que el operador pidió quitar cuando pidió una hoja por encargo: «con esta regla no
cometeremos errores de borrar búsquedas». Y no es de test: `nucleo/reset.py::reset_all()` es el ⏻ del
operador —«empezamos de cero»— así que en producción, tras un reset, la siguiente búsqueda hereda la caja de
la anterior y la estrena.

La causa: `sheet_id_for` compone `boot_id()` con el `task_id`, y `escalate.reset()` rebobina ese contador
mientras el sello sigue igual — sello estable × contador rebobinado = mismo id. V2-259 cerró la puerta del
REINICIO DE PROCESO con `boot_id()`; ésta es la misma avería por la puerta del reset, y el sello no podía
verla porque solo cambiaba al arrancar un proceso.

⚠️ Y el módulo del sello lo afirmaba al revés: su docstring decía «for TESTS … production never rewinds a
sequence», y era falso el día que se escribió — `reset_all` lo llamaba desde el primer momento. La clase que
ese módulo existe para cerrar estaba ocurriendo por la puerta que su autor creía de test.
"""
from nucleo import runtime_ids as R
from nucleo.flash import escalate


def test_rebobinar_el_contador_hace_ROTAR_el_sello():
    antes, seq_antes = R.boot_id(), R.next_seq("prueba.hoja")
    R.reset_seq("prueba.hoja")
    despues, seq_despues = R.boot_id(), R.next_seq("prueba.hoja")
    assert seq_antes == seq_despues, "el contador SÍ rebobina — eso no cambia, es lo que pide «de cero»"
    assert antes != despues, "el sello sobrevivió al rebobinado: los ids vuelven a chocar"


def test_y_por_eso_dos_encargos_separados_por_un_reset_NO_comparten_hoja():
    """El caso medido, sobre la función que compone el id de verdad."""
    from nucleo import sheets
    escalate.reset()
    primero = sheets.sheet_id_for(escalate._next_seq("escalate.task"))
    escalate.reset()                                  # el ⏻ del operador, o el reset entre casos del arnés
    segundo = sheets.sheet_id_for(escalate._next_seq("escalate.task"))
    assert primero != segundo, (
        "la segunda búsqueda hereda la caja de la primera y `begin_task(fresh=True)` la borra")


def test_el_contador_SIGUE_rebobinando_no_se_arregla_congelandolo():
    """Sensibilidad por el otro lado: dejar de rebobinar haría los ids crecer para siempre tras cada reset y
    no es lo que se pidió — lo que tiene que cambiar es el sello, no el contador."""
    escalate.reset()
    a = escalate._next_seq("escalate.task")
    escalate.reset()
    assert escalate._next_seq("escalate.task") == a == 1


def test_dentro_de_UNA_sesion_los_ids_siguen_siendo_estables():
    """El sello NO puede rotar por respirar: si cambiara en cada llamada, la hoja de un encargo vivo se movería
    debajo de quien la está mirando."""
    R.next_seq("prueba.estable")
    a = R.boot_id()
    for _ in range(5):
        R.next_seq("prueba.estable")
    assert R.boot_id() == a


def test_la_docstring_ya_NO_afirma_que_produccion_no_rebobina():
    """La afirmación falsa era el motivo de que nadie mirara aquí. Se queda escrito que no lo es."""
    d = R.reset_seq.__doc__ or ""
    # Se comprueba la CORRECCIÓN, no la ausencia de la frase: la docstring nueva CITA la vieja para contar el
    # fallo, y un guarda que confunda la explicación con la afirmación obliga a borrar el porqué (misma trampa
    # que el mensaje de `--start-at` unas horas antes).
    assert "was FALSE" in d, "la docstring vuelve a afirmar, sin más, que producción no rebobina"
    assert "reset_all" in d, "hay que decir QUIÉN rebobina en producción"
