"""Una página vacía CON entrega detrás no es «la búsqueda no está dando nada» (V2-370).

Medido en `search-buy-bicycle__es` (2026-08-27) — y lo que lo hace grave es que era la MEJOR ronda en días:
resultado 4, mecanismo 4, dos bicis reales entregadas (Trek 6500 SLR a 290 €, Specialized a 290 €, las dos
talla M y por debajo del tope). El último turno cerró así:

    «La página esa no está trayendo lo que pediste, así que la dejo.»

El juez lo archivó [alta] como afirmación falsa, y lo es. Pero **no la dijo el modelo: la dijimos nosotros.**
La nota que empuja `_hand_over` cuando una página no da ni una fila con nombre dice, literal, «esa página no
está dando lo que pidió», y el turno la repitió casi palabra por palabra.

Leído el prompt de ese turno antes de acusar a nadie: llevaba las CINCO filas con nombre y precio y la orden
de contarlas. No fue desobediencia — fue elegir entre dos hechos ciertos, y el que traía imperativo era el de
la nota. Es la forma de V2-222 otra vez: dos registros describiendo UN encargo, y el prompt sin rama para el
caso de en medio.

La nota se escribió para una búsqueda EN CURSO, donde decir «este sitio no da, cambio» es exactamente lo
correcto (V2-234). Disparada al final, después de haber entregado, esa misma frase pasa a ser el veredicto
del encargo entero y borra un resultado que sí existe. Lo que cambia no es el HECHO —la página sigue sin dar
nada, y callarlo dejaría al turno sin poder explicar por qué no llega nada nuevo— sino su ALCANCE.
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks
from widgets.results import data as SHEET

# La página que no da nada: enlaces de navegación de la propia web, sin un solo título.
CROMO = [
    {"title": "", "price": "300EUR", "url": "https://tienda.invalid/bicicletas/hasta-300"},
    {"title": "", "price": "", "url": "https://tienda.invalid/ayuda/envios"},
]
# Lo que YA se había entregado antes, tal cual salió en la ronda.
ENTREGADO = [
    {"title": "Bicicleta montaña Trek 6500 SLR mejorada Talla M", "price": "290 €",
     "url": "https://tienda.invalid/anuncio/trek"},
    {"title": "Bicicleta de Montaña Specialized", "price": "290 €",
     "url": "https://tienda.invalid/anuncio/specialized"},
]


@pytest.fixture
def task():
    tid = tasks.create("Busca una bicicleta de montaña de segunda mano en buen estado, talla M",
                       sheet="v370-hoja")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    yield tid
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()


def _nota(tid) -> str:
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    act_api._hand_over(tid, CROMO)
    notas = brain_notes.drain()
    assert notas, "sin nota no hay nada que medir"
    return " ".join(notas)


def _sembrar_hoja(items):
    SHEET.apply_action("present", {"sheet": "v370-hoja", "title": "Resultados", "items": items})


# ── con entrega detrás: el alcance es la PÁGINA ────────────────────────────────────────────────────────────

def test_la_ronda_medida_ya_no_licencia_el_veredicto_falso(task):
    """La frase SIGUE apareciendo, y tiene que aparecer: se NOMBRA para prohibirla. Un «no digas eso» sin
    decir cuál es «eso» no le da al modelo con qué contrastarse (V2-221). Lo que se comprueba es que llega
    como prohibición y no como orden, así que la distancia entre el «NUNCA» y la frase es el dato."""
    _sembrar_hoja(ENTREGADO)
    n = _nota(task)
    assert "no está dando lo que pidió" not in n, "la ORDEN vieja no puede seguir ahí"
    i_nunca, i_frase = n.find("NUNCA"), n.find("no está trayendo lo que pediste")
    assert i_nunca >= 0 and i_frase > i_nunca, "la frase tiene que venir DETRÁS del NUNCA que la prohíbe"
    assert "ni que lo dejas" in n


def test_el_HECHO_de_la_pagina_se_sigue_contando(task):
    """Callarse la página vacía sería el fallo contrario: el turno se quedaría sin poder explicar por qué no
    llega nada nuevo, que es justo lo que el operador está esperando oír."""
    _sembrar_hoja(ENTREGADO)
    n = _nota(task)
    assert "no ha salido ningún resultado con nombre" in n
    assert "enlaces de navegación" in n


def test_dice_que_la_busqueda_NO_ha_terminado(task):
    _sembrar_hoja(ENTREGADO)
    n = _nota(task)
    assert "NO el final de la búsqueda" in n
    assert "YA tiene resultados" in n


# ── sin nada entregado: la redacción de siempre, INTACTA ───────────────────────────────────────────────────

def test_con_la_hoja_VACIA_la_nota_no_cambia(task):
    """La sensibilidad que sostiene el arreglo. Sin entrega detrás, «esa página no está dando lo que pidió»
    es CIERTO y es lo útil — es V2-234, y perderlo cambiaría un defecto por otro: el turno volvería a servir
    enlaces de navegación como si fueran hallazgos."""
    _sembrar_hoja([])
    n = _nota(task)
    assert "esa página no está dando lo que pidió" in n
    assert "NO el final de la búsqueda" not in n


def test_una_fila_SIN_NOMBRE_no_cuenta_como_entrega(task, monkeypatch):
    """Una fila sin título no tiene identidad de cosa (V2-234), así que no puede sostener «ya te he dado
    algo»: si contara, bastaría con que la hoja tuviera cromo dentro para silenciar el aviso.

    ⚠️ Este caso se escribió primero sembrando la hoja con una fila sin título, y el desarme lo delató: quitar
    el filtro de nombre NO lo ponía en rojo. La razón es que la propia hoja ya descarta las filas sin título
    al escribirlas (`apply_action("present")` las tira), así que por esa vía el caso no podía tocar nunca la
    rama que dice medir. Se mide donde el filtro vive, contra el dato que la hoja DEVUELVE. La comprobación
    sigue valiendo la pena —es defensa en profundidad sobre un lector que no controla a su fuente— pero el
    test tiene que decir la verdad sobre qué recorre."""
    import widgets.results.data as _rd
    monkeypatch.setattr(_rd, "view_data",
                        lambda *a, **k: {"items": [{"title": "  ", "price": "10 €"}]})
    assert act_api._sheet_already_named(task) is False


def test_una_pagina_QUE_SI_DA_sigue_por_su_rama(task):
    """La tercera rama no se toca: con filas con nombre manda la nota de hallazgo de V2-223."""
    _sembrar_hoja(ENTREGADO)
    act_api._HANDED.pop(task, None)
    brain_notes.drain()
    act_api._hand_over(task, ENTREGADO)
    n = " ".join(brain_notes.drain())
    assert "ha SACADO esto de la página" in n
    assert "NO el final de la búsqueda" not in n


# ── el lector ──────────────────────────────────────────────────────────────────────────────────────────────

def test_sin_poder_leer_la_hoja_se_cae_a_la_redaccion_de_siempre(task, monkeypatch):
    """Dirección conservadora, y está razonada: sin entrega la redacción vieja es CORRECTA, y este caso solo
    existe cuando la hay. Al revés —callar la página vacía por si acaso— rompería el caso común."""
    import widgets.results.data as _rd
    monkeypatch.setattr(_rd, "view_data", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("hoja rota")))
    assert act_api._sheet_already_named(task) is False


def test_una_tarea_SIN_hoja_propia_no_hereda_la_entrega_de_otro_encargo():
    """La hoja PELADA es compartida (V2-259), así que leerla aquí dejaría que lo entregado por OTRO encargo
    callara el aviso de éste. Lo cazó un test que ya existía —la hoja pelada acumula filas dentro de la misma
    suite— y es el mismo defecto en producción, solo que ahí no se ve: `_sheet_of` cae a "" fail-soft."""
    tid = tasks.create("una tarea sin encargo detrás")     # sin `sheet=`
    _sembrar_hoja(ENTREGADO)                               # otra hoja, con entrega dentro
    SHEET.apply_action("append", {"sheet": "", "items": ENTREGADO})   # y la PELADA, también
    try:
        assert act_api._sheet_already_named(tid) is False
    finally:
        act_api._HANDED.pop(tid, None)
        brain_notes.drain()


def test_el_lector_mira_la_HOJA_del_encargo_y_no_el_registro_de_la_tarea(task):
    """Misma elección que V2-299 y por el mismo motivo: `has_results` solo existe si alguien llamó a
    `set_results`, y ahí la línea llegó a decir «SIN traer nada» con 21 filas en la hoja."""
    _sembrar_hoja(ENTREGADO)
    assert act_api._sheet_already_named(task) is True
    assert not (tasks.get(task) or {}).get("results"), "la premisa: el registro está vacío y la hoja no"
