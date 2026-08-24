"""`--start-at` y `--limit` acotan la tanda, y estaban en dos sitios con dos comportamientos (V2-280).

Medido el 2026-08-24 intentando arrancar la tanda de `search-buy`, que es literalmente lo que estos dos flags
existen para hacer. Las dos mitades del mismo fallo:

  · **El ORDEN de aplicación estaba invertido en el camino de correr.** `--limit` recortaba a los N PRIMEROS y
    LUEGO se buscaba el `--start-at` ahí dentro, así que la composición natural —«cuatro casos empezando por
    la bicicleta»— no seleccionaba nada y salía con «--start-at 'search-buy-bicycle__es' is not in the
    selected set». El mensaje apunta a la SELECCIÓN, que estaba bien; el problema era la aridad.
  · **Y `--list` ignoraba los dos.** Se usó para comprobar qué iba a correr la tanda y contestó por la
    selección entera: 19 casos donde iban a correr 4. Su propio comentario ya arreglaba esto mismo para
    `--segment` («un listado que contradice la corrida que pretende previsualizar es peor que no tener
    listado»), y la lección no se había aplicado a estos dos.

Y la parte que hace de esto una función compartida y no dos arreglos: **arreglar `--list` por su cuenta habría
sido PEOR que el fallo.** Ese camino ordenaba por (tier, locale, id) y el de correr respeta el orden de
`all_scenarios()`, que no es el mismo — comprobado, difieren desde el primer elemento. Un `--list` «arreglado»
habría previsualizado una tanda DISTINTA de la que corre, con toda la seguridad de un listado correcto.
"""
from tests.use_cases.e2e.agent import run as runmod
from tests.use_cases.e2e.agent import scenarios as SC


class _S:
    def __init__(self, i): self.id = i


_ROWS = [_S("a"), _S("b"), _S("c"), _S("d"), _S("e")]


def test_la_composicion_NATURAL_es_N_casos_DESDE_ese_id():
    rows, err = runmod.window_of(_ROWS, "c", 2)
    assert err == ""
    assert [s.id for s in rows] == ["c", "d"], (
        "es «dos casos empezando por c», no «los dos primeros y luego busca c»")


def test_y_ese_era_el_agujero_al_reves_no_selecciona_nada():
    """Sensibilidad: el orden invertido, hecho a mano, sobre los mismos datos."""
    recortado = _ROWS[:2]                              # lo que hacía `--limit` primero
    assert "c" not in [s.id for s in recortado], "por aquí salía «is not in the selected set»"


def test_cada_flag_por_su_cuenta_sigue_haciendo_lo_suyo():
    assert [s.id for s in runmod.window_of(_ROWS, "d", 0)[0]] == ["d", "e"]
    assert [s.id for s in runmod.window_of(_ROWS, "", 3)[0]] == ["a", "b", "c"]
    assert [s.id for s in runmod.window_of(_ROWS, "", 0)[0]] == ["a", "b", "c", "d", "e"]


def test_un_id_que_no_esta_es_un_ERROR_no_una_tanda_vacia():
    """Una tanda que no selecciona nada tiene que DECIRLO: correr cero casos en silencio se lee como éxito."""
    rows, err = runmod.window_of(_ROWS, "zzz", 2)
    assert "is not in the selected set" in err
    assert rows == _ROWS, "sin ventana válida no se recorta a ciegas"


def test_el_limite_MAYOR_que_la_lista_no_recorta():
    assert len(runmod.window_of(_ROWS, "", 99)[0]) == 5


# ── lo que obligó a compartir la función: los dos caminos NO ven el mismo orden ────────────────────────
def test_el_catalogo_NO_viene_ordenado_por_tier_locale_id():
    """La premisa del arreglo, afirmada aquí para que se entere quien la cambie.

    Si algún día `all_scenarios()` devolviera ya ordenado, este test se pone rojo y quien lo lea sabrá que
    `--list` puede volver a ordenar por su cuenta sin mentir. Mientras sea falso, no puede.
    """
    crudo = [s.id for s in SC.all_scenarios()]
    ordenado = sorted(crudo, key=lambda i: i)
    assert crudo != ordenado, (
        "el catálogo ya viene ordenado: revisa si `--list` puede reordenar sin separarse de la corrida")


def test_la_ventana_vive_UNA_vez():
    """Dos copias de esta decisión se separan sin avisar — es cómo nació este defecto."""
    import inspect
    src = inspect.getsource(runmod)
    # Se cuenta el `return` que lo PRODUCE, no la cadena: la docstring de `window_of` la cita al contar el
    # fallo medido, y un guarda que confundiera la explicación con una copia obligaría a borrar el porqué.
    assert src.count('return rows, f"--start-at') == 1, "el error volvió a construirse en dos sitios"
    assert src.count("window_of(") >= 3, "alguno de los dos caminos dejó de usar la función compartida"
