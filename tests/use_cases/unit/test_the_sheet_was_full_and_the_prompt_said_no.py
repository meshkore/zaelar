"""«Tenía resultados y contestó que no había novedades» — ¿mintió, o le contamos que no había nada?

Es la pregunta que decide la ATRIBUCIÓN del bloqueador más repetido del tablero. Leído desde el transcript,
ese turno parece una mentira del producto. Si en su prompt ponía que la tarea seguía atascada, entonces
contestó **exactamente lo que le pusimos delante**, y el defecto es nuestro.

Medido en `find-direct-flight-budget__es` (2026-08-28, plató 24/7): `sheet_named_ms` cae entre el turno 5 y
el 6; en los turnos **6, 7 y 8** el bloque vivo traía la cara de «sin avanzar» y CERO filas, con cuatro vuelos
con nombre en la hoja del encargo. El juez lo puntuó 2/5 por «retener la entrega y negar lo que el sistema le
mostraba». El sistema le mostraba lo contrario.

Barrido sobre los 353 informes guardados: de las **48** rondas cuya hoja llegó a tener nombres, **45** tienen
al menos un turno al que no se le dijo — **257 turnos** en total.

Esto NO dice dónde está la avería (`_found_candidates` ya cae a `_sheet_has_rows`, así que la resolución de la
caja del encargo es la sospechosa) y no intenta adivinarlo. Dice cuántas veces pasa, que es lo que convierte
una inferencia sobre una ronda en un número sobre muchas.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import verify as V

_T = {"sheet_named_ms": 1000.0}
_VIVO = "TAREAS DE FONDO EN CURSO (los brain workers las están resolviendo): «Busca vuelos» · sin avanzar"


def test_el_caso_MEDIDO_marca_sus_turnos():
    pc = [{"turn": 5, "at_ms": 900.0, "live_line": _VIVO, "sheet_rows": []},
          {"turn": 6, "at_ms": 1100.0, "live_line": _VIVO, "sheet_rows": []},
          {"turn": 7, "at_ms": 1200.0, "live_line": _VIVO, "sheet_rows": []}]
    got = V.sheet_hidden_from_the_prompt(pc, _T)
    assert got["n"] == 2 and [t["turn"] for t in got["turns"]] == [6, 7]


def test_un_turno_ANTERIOR_a_que_hubiera_filas_no_cuenta():
    """No se le puede ocultar lo que todavía no existe."""
    pc = [{"turn": 0, "at_ms": 500.0, "live_line": _VIVO, "sheet_rows": []}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_si_el_prompt_SÍ_lo_dice_no_es_ceguera():
    """Aunque no le diéramos los nombres: decirle que hay algo ya cambia lo que puede contestar."""
    pc = [{"turn": 6, "at_ms": 1100.0, "sheet_rows": [],
           "live_line": "TAREAS DE FONDO EN CURSO · la tarea YA HA ENCONTRADO algo, pero sus nombres aún no"}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_si_le_dimos_las_FILAS_menos_todavía():
    pc = [{"turn": 6, "at_ms": 1100.0, "live_line": _VIVO, "sheet_rows": ["Iberia directo 21:50"]}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_sin_BLOQUE_VIVO_no_hay_ceguera():
    """La tarea ya no está en curso: sus resultados se entregaron o se cerraron, y no había nada que contarle
    en ese turno. Cinco de los 262 turnos del barrido eran esto — contarlos habría inflado el número con la
    clase de caso que el propio hallazgo dice que NO es."""
    pc = [{"turn": 6, "at_ms": 1100.0, "live_line": "", "sheet_rows": []}]
    assert V.sheet_hidden_from_the_prompt(pc, _T)["n"] == 0


def test_sin_filas_con_nombre_NUNCA_no_hay_pregunta_que_hacer():
    """Y se distingue de «cero turnos ciegos»: no es lo mismo no tener el dato que tenerlo y salir a cero."""
    got = V.sheet_hidden_from_the_prompt([{"turn": 0, "at_ms": 1.0, "live_line": _VIVO}], {})
    assert got["n"] == 0 and got["measurable"] is False
    assert V.sheet_hidden_from_the_prompt([], _T)["measurable"] is True


def test_al_JUEZ_se_le_dice_que_NO_lo_puntúe_como_negar():
    """Medir esto y no contárselo al juez deja el veredicto igual de equivocado: la nota la pone él."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt":
                                {"n": 3, "measurable": True, "turns": [{"turn": 6}, {"turn": 7}, {"turn": 8}]}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" in txt and "6, 7, 8" in txt
    assert "NO lo puntúes como retener" in txt


def test_y_no_se_le_dice_nada_cuando_no_hubo_ceguera():
    """Un aviso que sale siempre deja de ser un aviso."""
    from tests.use_cases.e2e.agent import judge as J
    hechos = J.mechanism_facts({"sheet_hidden_from_the_prompt": {"n": 0, "measurable": True, "turns": []}})
    txt = "\n".join(hechos) if isinstance(hechos, list) else str(hechos)
    assert "NO SE LO DIJIMOS" not in txt
