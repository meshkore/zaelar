"""The note had navigation chrome at the front, and the turn described that (V2-234).

V2-223 made the extracted data reach the brain. What was not examined was WHICH three rows arrived: `items[:3]`, in
DOM order. Measured by the harness in `cheapest-monitor` (2026-08-20 23:44), with the raw extraction from the
`observer` / `navegador ↩` event, i=208 — this file reproduces it in full:

    1. title:""  price:"799EUR"  url:.../categorias/portatiles/basicos-hasta-799
    2. title:""  price:"200EUR"  url:.../categorias/smartphone-moviles/menos-de-200
    3. title:""  price:"200EUR"  url:.../categorias/tablets?...Max=200
    4. «Monitor Alurin CoreVision 120IPSLite 24" FHD 120Hz FreeSync»  99EUR  url de PRODUCTO + imagen
    5. «Monitor gaming PcCom Elysium 27" Fast IPS FHD 200Hz Adaptive Sync»  99EUR  url de PRODUCTO + imagen
    6. «PcCom Elysium Pro 27" Fast IPS QHD 200Hz»  99EUR

And what zaelar told the operator, literally: «what the page extracted is generic LAPTOP, MOBILE, AND TABLET
categories, not monitors». They are rows 1, 2, and 3, in that order. **The turn did not skip the fourth: the fourth
was not in the note.** It faithfully described the only thing we gave it, while there were three real monitors at
€99 with a link and photo two lines below.

This is not bad luck with that store: category and filter links appear BEFORE product cards in the DOM of any listing,
so a positional cutoff necessarily consumes the result. It is the same pattern as the 1500-character evidence cutoff,
which always consumes the end — where the good stuff is.

The criterion is structural, not a blacklist (tomorrow it will be another store): **a row without a title has no
identity as a thing, so it does not occupy the header**. It applies to a hotel, a car, an apartment in Los Angeles,
or a theater ticket, and to the listing no one has written yet. And NOTHING is discarded: what is below is counted and said.
"""
import pytest

from voice import brain_notes
from widgets.navegador import act_api, tasks

# The RAW extraction from the round, in its exact order.
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


# ── the measured case ─────────────────────────────────────────────────────────────────────────────────────────

def test_el_monitor_real_llega_al_cerebro(task):
    """The bar set by the harness: the user must be able to hear «Alurin CoreVision, 99 €» with its link."""
    n = _note(task)
    assert "Alurin CoreVision" in n
    assert "99EUR" in n
    assert "tienda.invalid/producto/alurin" in n


def test_y_el_cromo_de_navegacion_NO_ocupa_la_cabecera(task):
    """The other half, and the one that made the case fail: with the first three included, the turn described
    laptop categories in response to a question about monitors."""
    n = _note(task)
    cabecera = n.split("Nadie más lo sabe")[0]
    assert "categorias/portatiles" not in cabecera
    assert "categorias/smartphone-moviles" not in cabecera
    assert "categorias/tablets" not in cabecera


def test_la_hoja_tambien_lleva_los_resultados_delante(task):
    """Same blind cutoff, second consumer: `set_results` took `items[:5]` in DOM order, so the card showed two
    categories before the first monitor."""
    act_api._hand_over(task, CRUDO)
    items = (tasks.get(task) or {}).get("results", {}).get("items") or []
    assert [bool(i.get("title")) for i in items[:3]] == [True, True, True]
    assert items[0]["title"].startswith("Monitor Alurin")


def test_no_se_pierde_EN_SILENCIO_que_habia_mas(task):
    """Doctrine from `observability/evidence.py`: it is trimmed, not summarized, and it never stays silent about there
    being more. Here three rows remain outside the header, and the note SAYS so."""
    n = _note(task)
    assert "3 filas más" in n


# ── the page that only provides links ─────────────────────────────────────────────────────────────────────────

def test_sin_una_sola_fila_con_nombre_la_nota_lo_dice_y_da_salida(task):
    """Staying silent because only categories appeared would be worse: the turn would be unable to say «this page is
    not providing what you asked for, I am changing sites», which is true and useful. Nor are they served as findings."""
    act_api._hand_over(task, SOLO_CROMO)
    n = brain_notes.drain()[0]
    assert "NO ha sacado ni un resultado con nombre" in n
    assert "qué haces ahora" in n
    assert "SACADO esto de la página" not in n, "no puede sonar a que trae resultados"


# ── the criterion, raw ───────────────────────────────────────────────────────────────────────────────────────

def test_el_partido_conserva_el_orden_dentro_de_cada_mitad():
    """It is a PARTITION, not a quality sort: the latter would be interpretation, and that is the brain's job."""
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
    """Sensitivity on the other side: without chrome in the way, nothing changes from what V2-223 left working."""
    solo_buenos = CRUDO[3:]
    act_api._hand_over(task, solo_buenos)
    n = brain_notes.drain()[0]
    assert "Alurin CoreVision" in n and "filas más" not in n
    items = (tasks.get(task) or {}).get("results", {}).get("items") or []
    assert [i["title"] for i in items] == [i["title"] for i in solo_buenos]


def test_reextraer_la_misma_pagina_sigue_sin_ser_un_hallazgo_nuevo(task):
    """The dedup signature is calculated over the list AFTER partitioning; if it had remained based on DOM order,
    reordering would have changed the signature and each repeated extraction would count as new."""
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


# ── the SAME row three times is not three findings either ───────────────────────────────────────────────────
# A gift from the harness in the same round: the SECOND note contained three rows, and all three were the same Amazon
# ad URL. In other words, repetitions do not just add clutter — they OCCUPY the quota of three, so two of the three
# slots were spent saying the same thing. Deduplicating by URL before cutting recovers those two slots.
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
    """The absence of an address is not a shared identity: collapsing them would erase distinct results."""
    fresh, dropped = act_api.dedupe_by_url([{"title": "A"}, {"title": "B"}, {"title": "C"}])
    assert [i["title"] for i in fresh] == ["A", "B", "C"] and dropped == 0


def test_se_conserva_la_PRIMERA_aparicion():
    fresh, dropped = act_api.dedupe_by_url(
        [{"title": "primera", "url": "u"}, {"title": "segunda", "url": "u"}])
    assert [i["title"] for i in fresh] == ["primera"] and dropped == 1


# ── V2-240: the PHONE travels with the row ─────────────────────────────────────────────────────────────────
# The extractor already gets it from the card (node 4.32, rendered). Dropping it HERE would be V2-236 again: the
# data exists and no one sees it. In a service request it is the data that SOLVES the problem, and the thing that
# distinguishes a business listing from a directory link.

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
    """The signature includes the number: two listings with the same name and different phone numbers are not the same."""
    act_api._hand_over(task, SERVICIOS)
    brain_notes.drain()
    otro = [dict(SERVICIOS[0], tel="+34600111222"), SERVICIOS[1]]
    act_api._hand_over(task, otro)
    assert brain_notes.drain(), "un teléfono distinto es información nueva"
