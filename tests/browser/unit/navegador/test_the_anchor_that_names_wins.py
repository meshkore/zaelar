"""V2-324 — cuando varias anclas apuntan al MISMO anuncio, gana la que lo NOMBRA, no la primera del DOM.

Los 19 coches de un listado salían SIN nombre, y lo llamativo es que **ningún mecanismo estaba roto**:

  1. Cada anuncio tiene dos anclas a la misma ruta. En orden de DOM:
         [0] «Abrir detalles del anuncio»            ← enlace de accesibilidad, MUDO
         [1] «Skoda Octavia / 2.0TDI Selection 85kW» ← el nombre REAL
  2. El bucle de candidatos deduplica por `origin+pathname`, así que se quedaba con la PRIMERA y tiraba la
     que nombra.
  3. El bloque final «una etiqueta no es un nombre» borraba los 19 «Abrir detalles» repetidos (`times[t]>1`)
     — **y hacía bien**: «un dato que nombra a todas no nombra a ninguna».

O sea que el borrado era correcto y llegaba TARDE. El fallo estaba en elegir la peor de las dos anclas antes
de llegar a él: el nombre estaba en la página y lo tirábamos nosotros.

POR ESO EL ARREGLO NO ES UNA REGLA NUEVA sobre qué textos parecen nombres (esa es la cinta de correr, y era el
camino que estaba a punto de tomarse). Es dejar de descartar el dato que ya teníamos: las alternativas se
guardan y **decide el bloque que ya sabe cuál es genérica**, porque eso solo se puede saber al final, cuando se
ha contado qué texto se repite entre fichas.

⚠️ LA GARANTÍA QUE NO PODÍA ROMPERSE: el dedup existe para que «30 enlaces al mismo anuncio = 1 fila». Cambiar
QUIÉN gana no puede convertirse en cambiar CUÁNTAS filas salen — el primer test de abajo es ese contrato.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        p = browser.new_page(viewport={"width": 1280, "height": 900})
        yield p
        browser.close()


def _ficha(ruta: str, nombre: str, precio: str) -> str:
    """La forma MEDIDA en autoscout24: dos anclas a la misma ruta, la muda primero."""
    return (f'<article><a href="{ruta}">Abrir detalles del anuncio</a>'
            f'<a href="{ruta}"><h3>{nombre}</h3></a><span>{precio}</span></article>')


_LISTADO = "<html><body>" + "".join([
    _ficha("/anuncios/skoda-octavia-1", "Skoda Octavia 2.0TDI", "3.991 €"),
    _ficha("/anuncios/audi-a3-2", "Audi A3 Sportback 30 TDI", "4.531 €"),
    _ficha("/anuncios/citroen-c3-3", "Citroen C3 1.5 BlueHDi", "2.900 €"),
]) + "</body></html>"


def _filas(page, html):
    page.set_content(html)
    return page.evaluate(dom._JS_EXTRACT, 30)


def test_UNA_fila_por_anuncio_aunque_haya_varias_anclas(page):
    """El contrato del dedup, primero: si esto se rompe, el arreglo ha convertido «quién gana» en «cuántas»."""
    filas = _filas(page, _LISTADO)
    assert len(filas) == 3, f"tres anuncios, seis anclas → deben salir 3 filas, salieron {len(filas)}"
    assert len({f["url"] for f in filas}) == 3


def test_gana_el_ancla_que_NOMBRA_no_la_primera(page):
    filas = _filas(page, _LISTADO)
    nombres = [f["title"] for f in filas]
    assert all(n for n in nombres), f"alguna fila salió sin nombre: {nombres}"
    assert not any("Abrir detalles" in n for n in nombres), nombres
    assert nombres[0].startswith("Skoda Octavia")


def test_y_ANTES_del_arreglo_esas_filas_salian_MUDAS(page):
    """La sensibilidad del fixture: si el genérico no se repitiera entre fichas, el caso no probaría nada —
    el borrado de V2-234 no entraría y cualquier implementación pasaría."""
    page.set_content(_LISTADO)
    repetido = page.evaluate("""() => {
        const t=[...document.querySelectorAll('article > a:first-child')].map(a=>(a.innerText||'').trim());
        return t.length === 3 && new Set(t).size === 1;
    }""")
    assert repetido, "el fixture ya no reproduce: el ancla muda tiene que repetirse en las tres fichas"


def test_un_titulo_BUENO_no_se_pisa_con_la_alternativa(page):
    """Solo se recurre a la alternativa cuando el título elegido es genérico. Un nombre propio se queda."""
    html = ('<html><body><article>'
            '<a href="/anuncios/x-1"><h3>Seat Ibiza 1.0 TSI</h3></a>'
            '<a href="/anuncios/x-1">Ver ficha</a><span>7.500 €</span></article></body></html>')
    filas = _filas(page, html)
    assert len(filas) == 1
    assert filas[0]["title"].startswith("Seat Ibiza")


def test_sin_alternativa_buena_la_fila_se_queda_SIN_nombre(page):
    """La regla de V2-234 se respeta entera: con nada que sirva, sigue vacío. «Blanked rather than guessed» —
    un título vacío es una fila que el cerebro describe por su enlace; uno equivocado la describe con aplomo."""
    html = "<html><body>" + "".join(
        f'<article><a href="/anuncios/z-{i}">Abrir detalles del anuncio</a>'
        f'<a href="/anuncios/z-{i}">Abrir detalles del anuncio</a><span>{100+i} €</span></article>'
        for i in range(3)) + "</body></html>"
    filas = _filas(page, html)
    assert len(filas) == 3
    assert all(not f["title"] for f in filas), [f["title"] for f in filas]


def test_la_ALTERNATIVA_no_se_escapa_al_contrato(page):
    """`_alts` es andamiaje interno. El esquema de la fila es cerrado, y una clave de más viaja hasta la hoja."""
    for f in _filas(page, _LISTADO):
        assert "_alts" not in f and "_item" not in f, sorted(f)


def test_la_regla_del_DOS_PUNTOS_sigue_en_pie(page):
    """«Recomendado:» era la otra mitad de V2-234 y no la toca este cambio."""
    html = ('<html><body><article><a href="/anuncios/y-1">Recomendado:</a>'
            '<span>379,99 €</span></article></body></html>')
    filas = _filas(page, html)
    assert filas and not filas[0]["title"]
