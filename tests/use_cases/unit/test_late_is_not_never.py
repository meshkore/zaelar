"""«No entregó nunca» y «llegó tarde» mandan a arreglar cosas distintas, y el juez no sabía cuál era (V2-286).

`sheet_timing` mide desde V2-227 cuándo se abrió la hoja y cuándo se escribió la primera fila con nombre. En
todo ese tiempo **no lo ha leído nadie**: ni el juez ni el informe. Un número medido que nadie consume no es
una medida, es un fichero.

Y es justo el que separa las dos lecturas. Su ausencia se ve en el propio bloque del juez sobre la hoja, que
dice «Ojo con el MOMENTO: puede haberse llenado DESPUÉS del último turno» — se le advierte de la posibilidad y
nunca se le da el HECHO. Medido en la tanda del 2026-08-24 03:48, con los cuatro casos:

    monitor  4/5   primera fila 13,2 s ANTES del último turno   → había qué entregar, y entregó
    camera   2/5   primera fila 37,1 s ANTES                    → había qué entregar (falló la conducta)
    guitar   3/5   primera fila  1,6 s DESPUÉS                  → en la conversación no había nada
    bicycle  2/5   sin primera fila                             → no se encontró nada

⚠️ Y corrige una lectura mía: al ver que los tres entregaban en el turno 9 de 10 escribí que el problema
dominante era la LATENCIA. El número dice que no — en dos de los cuatro la hoja llevaba medio minuto llena
cuando se habló. La sospecha era razonable y el dato la desmiente, que es para lo que se mide.
"""
from tests.use_cases.e2e.agent import judge as J

_BASE = {"families_observed": ["worker", "widget"], "expected_signals": [], "missing_signals": [],
         "results_sheet": {"read": True, "n_items": 6, "n_named": 6, "n_backed": 6,
                           "n_sites_reported": 1, "titles": ["Nikon D3100"]}}


def _facts(after_s):
    m = dict(_BASE)
    m["sheet_timing"] = {"first_result_ms": 1000.0, "last_turn_ms": 1000.0 - (after_s * 1000.0),
                         "after_last_turn_s": after_s}
    return J.mechanism_facts(m)


def test_llegar_DESPUES_del_ultimo_turno_se_llama_latencia_y_no_ocultacion():
    f = _facts(1.6)
    assert "DESPUÉS del último turno" in f
    assert "LATENCIA" in f
    assert "no que zaelar se callara" in f, (
        "sin desmentir la lectura fácil, el juez la escribe igual — es lo que hizo en dos casos")


def test_llegar_ANTES_deja_el_fallo_donde_estaba_la_conducta():
    """La otra mitad, y es la que impide que esto se convierta en una amnistía: con la hoja llena mientras se
    habla, no entregar SÍ es conducta."""
    f = _facts(-37.1)
    assert "ANTES del último" in f
    assert "fallo de conducta" in f
    assert "LATENCIA" not in f


def test_sin_el_dato_no_se_afirma_ninguna_de_las_dos():
    """`None` es «no lo medí». Rellenarlo con un cero diría «llegó justo a tiempo», que es una afirmación."""
    m = dict(_BASE)
    m["sheet_timing"] = {"first_result_ms": None, "last_turn_ms": None, "after_last_turn_s": None}
    f = J.mechanism_facts(m)
    assert "LATENCIA" not in f and "fallo de conducta" not in f


def test_el_numero_se_CALCULA_en_la_ronda():
    """La mitad de cableado: el juez puede saber leerlo y la ronda no ponerlo (V2-199)."""
    import inspect

    from tests.use_cases.e2e.agent import run as R
    src = inspect.getsource(R)
    assert '"after_last_turn_s"' in src
    assert '"last_turn_ms"' in src, "sin el instante del último turno, la resta no se puede hacer"
