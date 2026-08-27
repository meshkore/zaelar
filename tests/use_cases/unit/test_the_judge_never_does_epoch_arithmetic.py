"""El juez no compara epochs de 13 cifras: el arnés se los da ya relativizados (V2-365).

Medido en `find-direct-flight-budget__es` (2026-08-27, ronda 15). El juez archivó como fallo de conducta MÁS
GRAVE de la sesión —[alta], «tenía datos concretos delante y no los dio»— esta prueba:

    «first_result_ms 1787816928677 vs turno a 1787816914617» → «la hoja ya tenía filas desde hacía ~30 s»

928677 es MAYOR que 914617. Las filas llegaron **14 segundos DESPUÉS** del turno que se acusaba. Signo
invertido y magnitud doblada. Y el bloque de prompt de ese turno, leído después en el log de sesión, no
llevaba ninguna fila: no había nada que entregar.

La prohibición en prosa ya estaba escrita desde V2-300 —«NO uses `first_result_ms` para acusar de retener»—
y no sirvió, porque el número seguía en el JSON justo debajo. Un guarda que prohíbe usar un dato que sigue
delante compite con el dato; el que funciona es no ponerlo.

Lo que hace la corrección es lo mismo que V2-300 hizo con `delivery_lag_s`: la cuenta la hace el arnés, que
la puede hacer exacta. Todos los instantes contra el MISMO cero, para que el juez pueda seguir cruzando una
fila con un turno —esa pregunta es legítima y es justo la que hay que poder responder— sin poder equivocarse
de signo al hacerlo.
"""
import json

from tests.use_cases.e2e.agent.judge import _clocks_relative


# Los dos números de la ronda, tal cual salieron del informe.
TURNO = 1787816914617.7258
FILAS = 1787816928677.772


def test_la_ronda_medida_ya_no_se_puede_leer_al_reves():
    mech = {"prompt_context": [{"at_ms": TURNO, "turn": 8}],
            "sheet_timing": {"first_result_ms": FILAS}}
    out = _clocks_relative(mech)
    turno = out["prompt_context"][0]["at_s"]
    filas = out["sheet_timing"]["first_result_s"]
    assert filas > turno, "las filas llegaron DESPUÉS del turno; ése es el hecho que se leyó al revés"
    assert round(filas - turno, 1) == 14.1, "y la distancia es de 14 s, no de los ~30 que escribió el juez"


def test_el_cero_es_el_primer_instante_medido():
    """Contra el mismo cero o no son comparables entre sí, que es justo lo que había que arreglar."""
    out = _clocks_relative({"a_ms": TURNO, "b_ms": FILAS})
    assert out == {"a_s": 0.0, "b_s": 14.1}


def test_ningun_epoch_crudo_sobrevive_al_json_del_juez():
    """El guarda de verdad: si mañana alguien añade un reloj nuevo, este test lo caza sin tocarlo."""
    mech = {"sheet_timing": {"first_result_ms": FILAS, "sheet_ms": TURNO},
            "prompt_context": [{"at_ms": TURNO}, {"at_ms": FILAS}],
            "hondo": {"lista": [{"mas_hondo": {"cuando_ms": FILAS}}]}}
    blob = json.dumps(_clocks_relative(mech))
    assert "17878169" not in blob, "un epoch crudo llegó al juez"
    assert "_ms" not in blob


def test_una_DURACION_no_se_toca():
    """`first_output_ms` son milisegundos TRANSCURRIDOS, no un instante. Relativizarlo lo convertiría en una
    hora del día y sería inventar un hecho — el error simétrico del que se está arreglando."""
    out = _clocks_relative({"at_ms": TURNO, "first_output_ms": 820, "latencia_ms": 0})
    assert out["first_output_ms"] == 820
    assert out["latencia_ms"] == 0
    assert out["at_s"] == 0.0


def test_sin_ningun_reloj_el_informe_pasa_intacto():
    mech = {"workers": {"spawned": 1}, "notas": ["sin relojes"]}
    assert _clocks_relative(mech) is mech


def test_el_informe_ORIGINAL_no_se_toca():
    """`mechanism_facts()` y el informe en disco siguen leyendo los epochs: la relativización es SOLO para el
    JSON que ve el juez. Mutar el original le cambiaría el dato a todo el que venga detrás."""
    mech = {"sheet_timing": {"first_result_ms": FILAS}}
    _clocks_relative(mech)
    assert mech == {"sheet_timing": {"first_result_ms": FILAS}}


def test_el_JSON_del_juez_sale_relativizado_y_lo_dice():
    """El cableado: que la función exista y no esté enchufada es el fallo clásico. Y el juez tiene que SABER
    que son segundos, o leerá un 14.1 como un epoch cortado."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/judge.py").read_text()
    assert "json.dumps(_clocks_relative(mech)" in src
    assert "SEGUNDOS desde el primer instante medido" in src
    assert "json.dumps(mech, ensure_ascii=False, indent=2)" not in src, "quedó un volcado crudo"
