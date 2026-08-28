"""V2-442 · un encargo pedido dos veces y ABSORBIDO no es trabajo duplicado.

El dedup (`dispatch.find_duplicate`) absorbe la segunda escalada sin lanzar worker. Cuando eso ocurre no hay
navegación duplicada: hay una decisión de escalar de más, que cuesta un turno. El juez recibía «el mismo
encargo se lanzó 2 veces … puntúa EFICIENCIA abajo» sin saber cuántos workers NACIERON, y lo archivó como
«duplica trabajo de navegación».

Medido el 2026-08-28 en `buy-known-product__us`: dos escaladas de texto IDÉNTICO (jaccard 1.0) y
`n_spawned: 1` — un solo worker. Cuarto caso esa noche de un instrumento acusando al producto de algo que no
hizo, y el que más veces se ha repetido en el barrido: de 214 rondas con la señal, 15 traen un duplicado
idéntico y en las cuatro últimas el dedup lo absorbió.

Y NO se absuelve en bloque, porque el caso real existe y está medido: el 24 y el 25 de agosto hubo grupos de
dos y tres encargos con TRES workers nacidos. Lo que decide es cuántos nacieron.
"""
from tests.use_cases.e2e.agent import judge


def _mech(n_spawned, n=2):
    return {"duplicate_errands": {"read": True, "worst": n, "identical_repeats": 1,
                                  "n_spawned": n_spawned,
                                  "groups": [{"n": n, "goal": "busca una bici", "identical": True}]}}


def _linea(mech):
    for l in judge.mechanism_facts(mech).splitlines():
        if "PIDIÓ" in l or "DUPLICADOS" in l:
            return l
    return ""


def test_absorbido_por_el_dedup_NO_se_puntua_como_trabajo_duplicado():
    l = _linea(_mech(1))
    assert "NO hubo trabajo duplicado" in l and "absorbió" in l
    assert "DUPLICADOS" not in l


def test_si_NACIERON_los_dos_sigue_siendo_el_defecto_de_siempre():
    """La mitad que impide que el arreglo sea una amnistía: con dos workers vivos el trabajo SÍ se hizo dos
    veces, y eso costó minutos de navegación reales el 24 y el 25 de agosto."""
    l = _linea(_mech(3))
    assert "DUPLICADOS" in l and "SÍ se hizo por duplicado" in l


def test_sin_saber_cuantos_nacieron_se_mantiene_la_ADVERTENCIA():
    """Fail-closed: «no lo sé» no puede absolver. Una ronda vieja sin el campo tiene que seguir leyéndose
    como antes, o el arreglo borraría hallazgos ya archivados."""
    m = _mech(1)
    m["duplicate_errands"].pop("n_spawned")
    assert "DUPLICADOS" in _linea(m)


def test_la_linea_DICE_cuantos_nacieron_en_las_dos_ramas():
    """Sin el número hay que volver a abrir el informe para saber de qué se habla — que es exactamente lo que
    costó descubrir este falso positivo."""
    assert "1 worker" in _linea(_mech(1))
    assert "3 worker" in _linea(_mech(3))
