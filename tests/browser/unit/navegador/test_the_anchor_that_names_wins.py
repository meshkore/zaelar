"""V2-324 — when several anchors point to the SAME listing, the one that NAMES it wins, not the first in the DOM.

The 19 cars in a listing appeared WITHOUT names, and remarkably **no mechanism was broken**:

  1. Each listing has two anchors to the same path. In DOM order:
         [0] «Abrir detalles del anuncio»            ← accessibility link, SILENT
         [1] «Skoda Octavia / 2.0TDI Selection 85kW» ← the REAL name
  2. The candidate loop deduplicated by `origin+pathname`, so it kept the FIRST one and discarded the
     one that names it.
  3. The final «a label is not a name» block removed the 19 repeated «Abrir detalles» entries (`times[t]>1`)
     — **and correctly so**: «data that names everything names nothing».

In other words, the removal was correct and came TOO LATE. The failure was choosing the worse of the two anchors
before reaching it: the name was on the page, and we were throwing it away ourselves.

THAT IS WHY THE FIX IS NOT A NEW RULE about which texts look like names (that is the treadmill, and it was the
path about to be taken). It is to stop discarding data we already had: the alternatives are saved and **the block
that already knows which one is generic decides**, because that can only be known at the end, after counting which
text is repeated across listings.

⚠️ THE GUARANTEE THAT COULD NOT BE BROKEN: deduplication exists so that «30 links to the same listing = 1 row».
Changing WHO wins cannot turn into changing HOW MANY rows come out — the first test below is that contract.
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
    """The MEASURED pattern on autoscout24: two anchors to the same path, the silent one first."""
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
    """The deduplication contract comes first: if this breaks, the fix has turned «who wins» into «how many»."""
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
    """The fixture's sensitivity: if the generic value were not repeated across listings, the case would prove nothing —
    the V2-234 removal would not kick in, and any implementation would pass."""
    page.set_content(_LISTADO)
    repetido = page.evaluate("""() => {
        const t=[...document.querySelectorAll('article > a:first-child')].map(a=>(a.innerText||'').trim());
        return t.length === 3 && new Set(t).size === 1;
    }""")
    assert repetido, "el fixture ya no reproduce: el ancla muda tiene que repetirse en las tres fichas"


def test_un_titulo_BUENO_no_se_pisa_con_la_alternativa(page):
    """The alternative is used only when the selected title is generic. A proper name stays."""
    html = ('<html><body><article>'
            '<a href="/anuncios/x-1"><h3>Seat Ibiza 1.0 TSI</h3></a>'
            '<a href="/anuncios/x-1">Ver ficha</a><span>7.500 €</span></article></body></html>')
    filas = _filas(page, html)
    assert len(filas) == 1
    assert filas[0]["title"].startswith("Seat Ibiza")


def test_sin_alternativa_buena_la_fila_se_queda_SIN_nombre(page):
    """The V2-234 rule is fully preserved: with nothing useful, it remains empty. «Blanked rather than guessed» —
    an empty title is a row the brain describes by its link; a wrong one describes it with confidence."""
    html = "<html><body>" + "".join(
        f'<article><a href="/anuncios/z-{i}">Abrir detalles del anuncio</a>'
        f'<a href="/anuncios/z-{i}">Abrir detalles del anuncio</a><span>{100+i} €</span></article>'
        for i in range(3)) + "</body></html>"
    filas = _filas(page, html)
    assert len(filas) == 3
    assert all(not f["title"] for f in filas), [f["title"] for f in filas]


def test_la_ALTERNATIVA_no_se_escapa_al_contrato(page):
    """`_alts` is internal scaffolding. The row schema is closed, and an extra key travels all the way to the sheet."""
    for f in _filas(page, _LISTADO):
        assert "_alts" not in f and "_item" not in f, sorted(f)


def test_la_regla_del_DOS_PUNTOS_sigue_en_pie(page):
    """«Recomendado:» was the other half of V2-234, and this change does not touch it."""
    html = ('<html><body><article><a href="/anuncios/y-1">Recomendado:</a>'
            '<span>379,99 €</span></article></body></html>')
    filas = _filas(page, html)
    assert filas and not filas[0]["title"]
