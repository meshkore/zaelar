"""V2-320 — un listado cuyas fichas no llevan ancla era INVISIBLE entero para el extractor.

Medido en vivo (2026-08-25, kayak.es/cars): la página mostraba «381 resultados» —Fiat 500 a 105 €, Peugeot
408 a 167 €— con 27 nodos hoja llevando precio, y `_JS_EXTRACT` devolvía CERO. Por construcción: el bucle de
candidatos solo recorre `a[href]`, y en Kayak cada oferta es un `<div>` cuyo único control es un botón «Ver
oferta». Los agregadores adoran el CTA de botón (coches, seguros, actividades) — que es exactamente la forma
de la familia «hoja vacía» del tablero (9/28 rondas).

Se prueba RENDERIZANDO un fixture local con la forma medida de la tarjeta real (radiografiada: sin headings,
sin img alt, sin strong; el nombre SOLO existe en el aria-label del botón). Un test de fuente daría por bueno
un recolector que compila; lo que importa es lo que sale de un DOM de verdad.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom

# La forma MEDIDA de la tarjeta de kayak (radiografía del 2026-08-25): div, precio en hoja con leyenda
# «Total», proveedor como primera línea, y el nombre completo solo en el aria-label del botón.
_KAYAK_SHAPED = """
<div id="grid">
  <div class="card"><span>bsp-auto</span><div><span aria-label="22 € en total">22 €</span><span>Total</span></div>
    <button aria-label="Ver oferta para Seat Ibiza de bsp-auto desde 22 €">Ver oferta</button></div>
  <div class="card"><span>Booking.com</span><div><span aria-label="17 € en total">17 €</span><span>Total</span></div>
    <button aria-label="Ver oferta para Renault Clio de Booking.com desde 17 €">Ver oferta</button></div>
  <div class="card"><span>OK Mobility</span><div><span aria-label="31 € en total">31 €</span><span>Total</span></div>
    <button aria-label="Ver oferta para Fiat Panda de OK Mobility desde 31 €">Ver oferta</button></div>
</div>
"""

# Y la forma ancla-por-ficha (Wallapop/Amazon): el camino de siempre, que no puede moverse ni un pelo.
_ANCHORED = """
<div>
  <a href="https://x.example/item/monitor-lg-1"><img alt="Monitor LG Full HD"><span>Monitor LG Full HD</span>
    <span>20 €</span></a>
  <a href="https://x.example/item/monitor-msi-2"><img alt="Monitor MSI Curvo"><span>Monitor MSI Curvo</span>
    <span>100 €</span></a>
</div>
"""


@pytest.fixture(scope="module")
def _page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def _extract(page, html: str, limit: int = 20):
    page.set_content(html)
    return page.evaluate(dom._JS_EXTRACT, limit)


def test_una_tarjeta_sin_ancla_sale_con_nombre_y_precio(_page):
    rows = _extract(_page, _KAYAK_SHAPED)
    assert len(rows) == 3, f"tres tarjetas con precio son tres filas, no {len(rows)}"
    por_precio = {r["price"]: r for r in rows}
    assert set(por_precio) == {"22 €", "17 €", "31 €"}
    # el nombre es el accesible LARGO de la tarjeta, no la leyenda corta del precio («22 € en total»)
    assert "Seat Ibiza" in por_precio["22 €"]["title"]
    assert "Renault Clio" in por_precio["17 €"]["title"]
    # sin ancla no hay URL, y el contrato lo permite (las filas de teléfono tampoco llevan importe)
    assert all(not r.get("url") for r in rows)


def test_el_camino_de_anclas_no_se_mueve_ni_un_pelo(_page):
    """La guarda del recolector nuevo es que SOLO dispara con el de anclas vacío: en un listado con anclas
    las filas salen por el camino medido de siempre — con URL — y ninguna fila fantasma se cuela al lado."""
    rows = _extract(_page, _ANCHORED)
    assert len(rows) == 2
    assert all(r.get("url", "").startswith("https://x.example/item/") for r in rows)
    assert [r["title"] for r in rows] == ["Monitor LG Full HD", "Monitor MSI Curvo"]


def test_una_pagina_sin_ningun_precio_sigue_dando_cero(_page):
    """El formulario de rentalcars (radiografiado: 129 anclas, cero importes) tiene que seguir saliendo
    vacío: cero filas de un formulario es la respuesta HONESTA, no un defecto."""
    rows = _extract(_page, "<form><input placeholder='Recogida'><button>Buscar</button></form><a href='https://x.example/ayuda'>Ayuda</a>")
    assert rows == []
