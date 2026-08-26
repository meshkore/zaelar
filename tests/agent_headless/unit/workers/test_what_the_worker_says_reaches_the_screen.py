"""V2-345 — lo que el worker NARRA es la señal más rica que tenemos, y no salía en ninguna pantalla.

Medido en la sesión `7575e81a` (2026-08-26), los 21,6 min del encargo del coche: **82 narraciones, una cada
16 s**, todas a observabilidad y ninguna a la pestaña de Proceso. Son mejores que cualquier frase que podamos
generar nosotros porque llevan el sitio, el precio, el modelo y el PORQUÉ del paso siguiente:

    «Wallapop devuelve candidatos pero mayormente coches viejos (pre-2016). Necesito filtros de año.»
    «¡Bien! Tengo más opciones dentro del presupuesto. Voy a revisar el Renault Laguna Coupé (11.650€).»

Frecuencia entregada en la pestaña, medida por REPLAY sobre esa misma sesión:

    antes de nada …………………………… una línea cada 162 s
    con V2-343 (pasos del navegador) … una línea cada  59 s
    con esto ………………………………………… una línea cada  10 s

El «💬» NO es decoración. El worker AFIRMA cosas, y esta casa ya pagó que una afirmación suya se tomara por un
hecho comprobado (V2-249: escribió «Recordatorio PROGRAMADO» en memoria durable sin poder programar nada). En
este anillo su prosa convive con lo que SÍ hemos verificado —«14 resultados en la página»— así que tienen que
distinguirse a simple vista. Prefijar en vez de inventar un canal nuevo es el patrón que ya usa el muro de chat.
"""
import pytest

from nucleo import sheets as SH


class _Rec:
    def __init__(self, tid="t1"):
        self.task_id, self.phases, self.surface = tid, [], ""


def test_the_worker_prose_is_marked_apart_from_verified_fact():
    """Lo que distingue una afirmación del worker de un hecho nuestro tiene que verse sin leer."""
    r = _Rec()
    SH.record_phase(r, "14 resultados en la página", 150)
    SH.record_phase(r, "💬 ¡Tengo resultados! Veo varios coches diésel dentro del presupuesto.", 150)
    dichas = [p["s"] for p in r.phases]
    assert not dichas[0].startswith("💬"), "un hecho que verificamos nosotros no se marca como dicho por él"
    assert dichas[1].startswith("💬")


def test_two_different_narrations_both_get_through():
    """Son distintas casi siempre —cada una cuenta otro paso— así que el dedup no las estorba."""
    r = _Rec()
    SH.record_phase(r, "💬 Aplico el filtro de precio máximo 12.000€.", 150)
    SH.record_phase(r, "💬 El filtro no se aplicó por URL. Uso el filtro visual.", 150)
    assert len(r.phases) == 2


def test_the_same_narration_twice_is_still_ONE_line():
    """SENSIBILIDAD: el dedup sigue mandando. Un worker que se repite no es progreso."""
    r = _Rec()
    for _ in range(3):
        SH.record_phase(r, "💬 Sigo haciendo scroll para llegar a los resultados.", 150)
    assert len(r.phases) == 1


def test_a_whole_errand_fits_in_the_ring():
    """El encargo medido produce 127 líneas. Con el anillo en 40 la frase de cierre de la pestaña —«Esto es lo
    que hizo para llegar aquí»— dejaba de ser cierta al acabar, que es cuando más se lee."""
    assert SH.PHASES_KEPT >= 127, "el anillo tiene que caber un encargo real medido, no un número redondo"
    r = _Rec()
    for i in range(127):
        SH.record_phase(r, f"💬 paso {i}", SH.PHASES_KEPT)
    assert len(r.phases) == 127


def test_the_ring_is_still_a_ring():
    """SENSIBILIDAD la otra dirección: subir el techo no puede volverse guardarlo todo. Esto es lo que el
    operador MIRA; la auditoría entera vive en observabilidad, con su evidencia."""
    r = _Rec()
    for i in range(SH.PHASES_KEPT + 25):
        SH.record_phase(r, f"💬 paso {i}", SH.PHASES_KEPT)
    assert len(r.phases) == SH.PHASES_KEPT


def test_the_session_actually_pushes_it():
    """Guarda de CABLEADO sobre la fuente SIN comentarios: la decisión sin llamante es el arreglo que no existe
    (V2-199), y este fichero encontró el código exactamente en ese estado — `_emit_note` llevaba el texto bueno
    a observabilidad y a nadie más."""
    from pathlib import Path
    src = "\n".join(ln for ln in Path("nucleo/workers/session.py").read_text().splitlines()
                    if not ln.strip().startswith("#"))
    i = src.index("def _emit_note")
    cuerpo = src[i:i + 2600]
    assert "record_phase" in cuerpo, "la narración no sale del visor"
    assert '"💬 "' in cuerpo, "sin el marcador, su afirmación se lee como hecho verificado"
