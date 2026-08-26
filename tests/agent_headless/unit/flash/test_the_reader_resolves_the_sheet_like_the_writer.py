"""El escritor resolvía la hoja por dos caminos y el lector por uno (V2-352).

Medido en vivo el 2026-08-26, `search-buy-used-car` ronda 12. La ronda salió **1/5**, y su bloqueador nº1 fue
«zaelar tuvo resultados reales delante durante más de 4 minutos y dijo repetidamente que no había nada»: el
operador preguntó cinco veces «¿ya tienes algo?» y recibió cinco negativas mientras la hoja acumulaba DOCE
coches con nombre, precio y enlace (Mercedes Clase A, Chrysler Sebring, Alfa Tonale, Golf Variant, BMW 520d…).

No fue el modelo. El guarda DETERMINISTA que existe justo para esto —`delivery.sheet_delivery_backstop`, V2-305—
disparó su evento de silencio NUEVE veces, y V2-336 (que hizo el silencio visible con sus entradas) dejó el
porqué escrito en el propio evento:

    38,0s  rows=0  goal=''   |   325,5s  rows=0  goal=''      ← las nueve iguales

`rows=0` con doce filas en la hoja. Al backstop nunca le llegaron.

LA ASIMETRÍA. La hoja de un encargo se resuelve desde la pestaña del navegador, y hay DOS caminos:

  · el SELLO de la pestaña (`tasks.get(tid)["sheet"]`) — durable, sobrevive al worker (V2-281), pero **se
    escribe una sola vez, en `create()`**: si el registro aún no tenía hoja sellada en ese instante, queda
    vacío PARA SIEMPRE (lo dice el propio comentario de `tasks.create`);
  · el REGISTRO de sesiones vivas (`dispatch.sheet_for_nav_task`) — sabe contestar mientras el worker viva.

El ESCRITOR (`act_api._sheet_for`, que alimenta `_hand_over`) usa los dos: sello, y si está vacío, el registro.
Por eso las doce filas aterrizaron bien en `results::9a37af-1`. Los LECTORES —`_sheet_has_rows`, la cara «YA
TIENE RESULTADOS», y `_sheet_top_rows`, del que come el backstop— se paraban en el primero:

    sheet = tasks.get(tid)["sheet"]
    if not sheet:
        return []          # ← ciego

Escribe bien y lee mal: la misma forma que V2-350 (dos puertas, respuestas distintas al mismo worker) y que
V2-348 (una rama que faltaba en un solo lado). Y la tarjeta FANTASMA que el arnés reporta en las dos rondas es
el otro síntoma del mismo cero: `tasks.create` avisa de que una hoja sin resolver manda los hallazgos a la caja
`results` desnuda, «la que no es de nadie».

EL ORDEN NO CAMBIA, y es deliberado: primero el sello, que es lo único que sigue ahí cuando al worker le
relevan o se muere (V2-281). El registro es RESPALDO, exactamente como en el escritor — ni más ni menos.
"""
import pytest

from nucleo.flash import live_blocks as LB

FILAS = [{"title": "MERCEDES-BENZ Clase A 200 d", "price": "39.900 €"},
         {"title": "CHRYSLER Sebring 200C 2.0CRD Limited", "price": "2.500 €"},
         {"title": "VOLKSWAGEN Golf Variant 2.0TDI Life 85kW", "price": "11.900 €"}]


@pytest.fixture
def plató(monkeypatch):
    """Una pestaña, una hoja con filas, y un mando para decir si la pestaña lleva sello o no.

    Se parchean los ATRIBUTOS de los módulos reales, nunca `sys.modules`: los lectores hacen
    `from widgets.navegador import tasks` DENTRO de la función, y eso lee el atributo del paquete ya importado,
    así que sustituir la entrada de `sys.modules` solo funciona si nadie lo importó antes — verde en solitario y
    rojo con la suite entera, que es como se cazó aquí.
    """
    from nucleo import dispatch as _disp
    from widgets.navegador import tasks as _t
    from widgets.results import data as _sd
    estado = {"sello": "", "registro": ""}
    monkeypatch.setattr(_t, "get", lambda tid: {"sheet": estado["sello"]} if tid == "t1" else None)
    monkeypatch.setattr(_t, "active_summaries",
                        lambda limit=3: [("t1", "Búscame un coche de segunda mano diésel por menos de 12.000 €")])
    monkeypatch.setattr(_sd, "view_data",
                        lambda sheet, *a, **k: {"items": FILAS} if sheet == "results::9a37af-1" else {"items": []})
    monkeypatch.setattr(_disp, "sheet_for_nav_task", lambda tid: estado["registro"])
    return estado


def test_con_sello_se_lee_por_el_sello(plató):
    """El camino de siempre, intacto: el sello manda y el registro ni se consulta (V2-281)."""
    plató["sello"] = "results::9a37af-1"
    plató["registro"] = "results::OTRA-COSA"
    assert LB._sheet_top_rows("t1", 3)
    assert "Clase A" in LB._sheet_top_rows("t1", 3)[0]
    assert LB._sheet_has_rows("t1") is True


def test_SIN_sello_el_lector_pregunta_al_registro_como_hace_el_escritor(plató):
    """El defecto medido: la pestaña se creó antes de que su registro tuviera hoja, así que el sello quedó
    vacío para siempre. El escritor sale adelante por el respaldo; el lector se quedaba ciego."""
    plató["sello"] = ""
    plató["registro"] = "results::9a37af-1"
    filas = LB._sheet_top_rows("t1", 3)
    assert filas, "rows=0 con doce coches en la hoja: es el silencio de las nueve veces"
    assert "Clase A" in filas[0]
    assert LB._sheet_has_rows("t1") is True


def test_y_entonces_el_backstop_de_entrega_SI_ve_las_filas(plató):
    """La consecuencia entera, en el punto donde se midió: `any_live_task_rows` es lo que come el backstop."""
    plató["sello"] = ""
    plató["registro"] = "results::9a37af-1"
    goal, filas = LB.any_live_task_rows(3)
    assert len(filas) == 3, "esto es el `rows=0` del evento de silencio, que salió nueve veces"
    assert "coche de segunda mano" in goal, "sin el encargo, el backstop no puede juzgar frescura"


def test_sin_sello_y_sin_registro_no_se_inventa_nada(plató):
    """El lado conservador: dos caminos agotados es «no hay hoja», no una hoja cualquiera. Caer en la caja
    `results` desnuda sería anunciar las filas de otro encargo."""
    plató["sello"] = ""
    plató["registro"] = ""
    assert LB._sheet_top_rows("t1", 3) == []
    assert LB._sheet_has_rows("t1") is False
    assert LB.any_live_task_rows(3) == ("", [])


def test_una_hoja_que_existe_pero_esta_VACIA_no_es_un_hallazgo(plató):
    """Resolver la dirección no es tener filas: una hoja recién abierta resuelve bien y no trae nada."""
    plató["sello"] = "results::recien-abierta"
    plató["registro"] = ""
    assert LB._sheet_top_rows("t1", 3) == []
    assert LB._sheet_has_rows("t1") is False
