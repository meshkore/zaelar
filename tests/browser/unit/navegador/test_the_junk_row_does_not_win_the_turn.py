"""La nota llevaba delante el cromo de navegación, y el turno describió eso (V2-234).

V2-223 hizo que lo extraído llegara al cerebro. Lo que no se miró es QUÉ tres filas llegaban: `items[:3]`, en
orden de DOM. Medido por el arnés en `cheapest-monitor` (2026-08-20 23:44), con la extracción cruda del evento
`observer` / `navegador ↩`, i=208 — este fichero la reproduce entera:

    1. title:""  price:"799EUR"  url:.../categorias/portatiles/basicos-hasta-799
    2. title:""  price:"200EUR"  url:.../categorias/smartphone-moviles/menos-de-200
    3. title:""  price:"200EUR"  url:.../categorias/tablets?...Max=200
    4. «Monitor Alurin CoreVision 120IPSLite 24" FHD 120Hz FreeSync»  99EUR  url de PRODUCTO + imagen
    5. «Monitor gaming PcCom Elysium 27" Fast IPS FHD 200Hz Adaptive Sync»  99EUR  url de PRODUCTO + imagen
    6. «PcCom Elysium Pro 27" Fast IPS QHD 200Hz»  99EUR

Y lo que zaelar le dijo al operador, literal: «lo que ha sacado la página son categorías genéricas de PORTÁTILES,
MÓVILES Y TABLETS, no monitores». Son las filas 1, 2 y 3, en su orden. **El turno no se saltó la cuarta: la
cuarta no estaba en la nota.** Describió fielmente lo único que le dimos, mientras había tres monitores reales a
99 € con enlace y foto dos líneas más abajo.

No es mala suerte de esa tienda: los enlaces de categoría y de filtro salen ANTES que las fichas de producto en
el DOM de cualquier listado, así que un corte por posición se come el resultado por construcción. Es la misma
forma que el corte de evidencia a 1500 caracteres, que siempre se come el final — donde está lo bueno.

El criterio es estructural y no una lista negra (mañana es otra tienda): **una fila sin título no tiene identidad
de cosa, así que no ocupa la cabecera**. Vale para un hotel, un coche, un piso en Los Ángeles o una entrada de
teatro, y para el listado que nadie ha escrito todavía. Y NO se tira nada: lo de abajo se cuenta y se dice.
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks

# La extracción CRUDA de la ronda, en su orden exacto.
CRUDO = [
    {"title": "", "price": "799EUR", "url": "https://tienda.invalid/categorias/portatiles/basicos-hasta-799"},
    {"title": "", "price": "200EUR", "url": "https://tienda.invalid/categorias/smartphone-moviles/menos-de-200"},
    {"title": "", "price": "200EUR", "url": "https://tienda.invalid/categorias/tablets?Max=200"},
    {"title": 'Monitor Alurin CoreVision 120IPSLite 24" FHD 120Hz FreeSync', "price": "99EUR",
     "url": "https://tienda.invalid/producto/alurin", "image": "a.jpg"},
    {"title": 'Monitor gaming PcCom Elysium 27" Fast IPS FHD 200Hz Adaptive Sync', "price": "99EUR",
     "url": "https://tienda.invalid/producto/elysium", "image": "b.jpg"},
    {"title": 'PcCom Elysium Pro 27" Fast IPS QHD 200Hz', "price": "99EUR",
     "url": "https://tienda.invalid/producto/elysium-pro"},
]
SOLO_CROMO = CRUDO[:3]


@pytest.fixture
def task():
    tid = tasks.create("un monitor bueno para trabajar que no sea carísimo")
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()
    yield tid
    act_api._HANDED.pop(tid, None)
    brain_notes.drain()


def _note(task) -> str:
    act_api._hand_over(task, CRUDO)
    notes = brain_notes.drain()
    assert notes, "sin nota no hay nada que medir"
    return notes[0]


# ── el caso medido ───────────────────────────────────────────────────────────────────────────────────────────

def test_el_monitor_real_llega_al_cerebro(task):
    """El listón que puso el arnés: que el usuario pueda oír «Alurin CoreVision, 99 €» con su enlace."""
    n = _note(task)
    assert "Alurin CoreVision" in n
    assert "99EUR" in n
    assert "tienda.invalid/producto/alurin" in n


def test_y_el_cromo_de_navegacion_NO_ocupa_la_cabecera(task):
    """La otra mitad, y es la que hacía fallar el caso: con las tres primeras dentro, el turno describía
    categorías de portátiles ante una pregunta sobre monitores."""
    n = _note(task)
    cabecera = n.split("Nadie más lo sabe")[0]
    assert "categorias/portatiles" not in cabecera
    assert "categorias/smartphone-moviles" not in cabecera
    assert "categorias/tablets" not in cabecera


def test_la_hoja_tambien_lleva_los_resultados_delante(task):
    """Mismo corte ciego, segundo consumidor: `set_results` se llevaba `items[:5]` en orden de DOM, así que la
    tarjeta enseñaba dos categorías antes que el primer monitor."""
    act_api._hand_over(task, CRUDO)
    items = (tasks.get(task) or {}).get("results", {}).get("items") or []
    assert [bool(i.get("title")) for i in items[:3]] == [True, True, True]
    assert items[0]["title"].startswith("Monitor Alurin")


def test_no_se_pierde_EN_SILENCIO_que_habia_mas(task):
    """Doctrina de `observability/evidence.py`: se recorta, no se resume, y nunca se calla que había más. Aquí
    quedan tres filas fuera de la cabecera y la nota lo DICE."""
    n = _note(task)
    assert "3 filas más" in n


# ── la página que solo da enlaces ────────────────────────────────────────────────────────────────────────────

def test_sin_una_sola_fila_con_nombre_la_nota_lo_dice_y_da_salida(task):
    """Callarse porque solo salieron categorías sería peor: el turno se quedaría sin poder decir «esta página no
    está dando lo que pediste, cambio de sitio», que es cierto y útil. Y tampoco se sirven como hallazgos."""
    act_api._hand_over(task, SOLO_CROMO)
    n = brain_notes.drain()[0]
    assert "NO ha sacado ni un resultado con nombre" in n
    assert "qué haces ahora" in n
    assert "SACADO esto de la página" not in n, "no puede sonar a que trae resultados"


# ── el criterio, en crudo ────────────────────────────────────────────────────────────────────────────────────

def test_el_partido_conserva_el_orden_dentro_de_cada_mitad():
    """Es un PARTIDO, no una ordenación por calidad: eso último sería interpretar, y ahí manda el cerebro."""
    named, unnamed = act_api.by_identity(CRUDO)
    assert [i["title"] for i in named] == [c["title"] for c in CRUDO[3:]]
    assert [i["url"] for i in unnamed] == [c["url"] for c in CRUDO[:3]]


def test_un_titulo_de_solo_espacios_no_es_identidad():
    named, unnamed = act_api.by_identity([{"title": "   ", "price": "9 €"}, {"title": "Silla", "price": "9 €"}])
    assert [i["title"] for i in named] == ["Silla"]
    assert len(unnamed) == 1


def test_lo_que_no_es_un_dict_no_entra_por_ninguna_de_las_dos():
    named, unnamed = act_api.by_identity(["basura", None, {"title": "Silla"}])
    assert len(named) == 1 and unnamed == []


def test_una_lista_entera_con_nombre_se_comporta_como_siempre(task):
    """Sensibilidad por el otro lado: sin cromo de por medio no cambia nada de lo que V2-223 dejó funcionando."""
    solo_buenos = CRUDO[3:]
    act_api._hand_over(task, solo_buenos)
    n = brain_notes.drain()[0]
    assert "Alurin CoreVision" in n and "filas más" not in n
    items = (tasks.get(task) or {}).get("results", {}).get("items") or []
    assert [i["title"] for i in items] == [i["title"] for i in solo_buenos]


def test_reextraer_la_misma_pagina_sigue_sin_ser_un_hallazgo_nuevo(task):
    """La firma de dedup se calcula sobre la lista YA repartida; si se hubiera quedado sobre el orden de DOM,
    reordenar habría cambiado la firma y cada extracción repetida contaría como nueva."""
    act_api._hand_over(task, CRUDO)
    brain_notes.drain()
    act_api._hand_over(task, CRUDO)
    assert brain_notes.drain() == []


def test_la_fase_cuenta_RESULTADOS_y_no_filas():
    """«12 resultados en la página» con nueve enlaces de categoría dentro es una cifra que el operador lee y se
    cree. Y contar solo los que tienen nombre no calla nada: `progress.found(0)` dice «sin resultados en esta
    página», que es exactamente lo que hace falta para que el worker cambie de sitio en vez de insistir.

    GUARDA DE FUENTE, y se dice por qué: esa línea vive dentro del handler HTTP de `extract`, que exige una
    pestaña de navegador viva. Lo que se puede comprobar sin navegador es que la cuenta sale del reparto y no de
    `len(items)` — y eso es justo lo que una regresión desharía sin fallar con ruido.
    """
    import inspect

    src = inspect.getsource(act_api.navegador_act)
    rama = src[src.index('if action == "extract":'):]
    rama = rama[:rama.index('if action in (')]
    assert "by_identity(items)" in rama, "el reparto tiene que ocurrir ANTES de contar"
    assert "_progress.found(len(_named))" in rama
    assert "_progress.found(len(items))" not in rama, "contar filas cuenta el cromo como resultado"


# ── la MISMA fila tres veces tampoco son tres hallazgos ──────────────────────────────────────────────────────
# Regalo del arnés de la misma ronda: la SEGUNDA nota llevaba tres filas y las tres eran la misma url de
# anuncio de Amazon. O sea que las repeticiones no solo ensucian — OCUPAN el cupo de tres, así que dos de los
# tres huecos se gastaban en decir lo mismo. Deduplicar por url antes de cortar recupera esos dos huecos.
ANUNCIO = "https://aax-eu-zaz.amazon.es/x/c/JLv"
REPETIDO = [
    {"title": "", "price": "00 €", "url": ANUNCIO},
    {"title": "", "price": "00 €", "url": ANUNCIO},
    {"title": "", "price": "00 €", "url": ANUNCIO},
    {"title": "Silla de oficina ergonómica", "price": "129 €", "url": "https://tienda.invalid/producto/silla"},
]


def test_la_misma_url_no_ocupa_tres_huecos(task):
    act_api._hand_over(task, REPETIDO)
    n = brain_notes.drain()[0]
    assert n.count(ANUNCIO) <= 1, "la misma dirección repetida no informa tres veces"
    assert "Silla de oficina" in n, "el resultado real tiene que caber una vez recuperados los huecos"


def test_las_repetidas_se_CUENTAN_no_se_callan(task):
    act_api._hand_over(task, REPETIDO)
    assert "2 repetidas" in brain_notes.drain()[0]


def test_una_fila_SIN_url_no_se_deduplica_contra_otra_sin_url():
    """La ausencia de dirección no es una identidad compartida: colapsarlas borraría resultados distintos."""
    fresh, dropped = act_api.dedupe_by_url([{"title": "A"}, {"title": "B"}, {"title": "C"}])
    assert [i["title"] for i in fresh] == ["A", "B", "C"] and dropped == 0


def test_se_conserva_la_PRIMERA_aparicion():
    fresh, dropped = act_api.dedupe_by_url(
        [{"title": "primera", "url": "u"}, {"title": "segunda", "url": "u"}])
    assert [i["title"] for i in fresh] == ["primera"] and dropped == 1


# ── V2-240: el TELÉFONO viaja con la fila ────────────────────────────────────────────────────────────────────
# El extractor ya lo saca de la tarjeta (nodo 4.32, renderizado). Dejarlo caer AQUÍ sería V2-236 otra vez: el
# dato existe y nadie lo ve. En un encargo de servicio es el dato que RESUELVE, y el que separa una ficha de
# negocio del enlace a un directorio.

SERVICIOS = [
    {"title": "Fontanería Aqua 24h", "price": "", "tel": "+34910123456",
     "url": "https://guia.invalid/fontaneros/madrid/aqua-24h"},
    {"title": "Reparalia Fontaneros", "price": "", "tel": "915 55 99 88",
     "url": "https://guia.invalid/fontaneros/madrid/reparalia"},
]


def test_el_numero_al_que_llamar_LLEGA_a_la_conversacion(task):
    act_api._hand_over(task, SERVICIOS)
    n = brain_notes.drain()[0]
    assert "+34910123456" in n, "el teléfono se extraía y se caía por el camino"
    assert "Fontanería Aqua 24h" in n


def test_una_ficha_sin_precio_no_se_queda_sin_fila(task):
    act_api._hand_over(task, SERVICIOS)
    n = brain_notes.drain()[0]
    assert "Reparalia" in n and "915 55 99 88" in n


def test_el_mismo_listado_dos_veces_sigue_sin_ser_un_hallazgo_nuevo(task):
    act_api._hand_over(task, SERVICIOS)
    brain_notes.drain()
    act_api._hand_over(task, SERVICIOS)
    assert brain_notes.drain() == []


def test_si_CAMBIA_el_telefono_es_otro_hallazgo(task):
    """La firma incluye el número: dos fichas con el mismo nombre y distinto teléfono no son la misma."""
    act_api._hand_over(task, SERVICIOS)
    brain_notes.drain()
    otro = [dict(SERVICIOS[0], tel="+34600111222"), SERVICIOS[1]]
    act_api._hand_over(task, otro)
    assert brain_notes.drain(), "un teléfono distinto es información nueva"
