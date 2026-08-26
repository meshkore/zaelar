"""V2-334 — una ruta que comparten decenas de anclas no es la ficha de nada.

Es la regla que este fichero ya aplica al ANCESTRO —«un dato que nombra a todas no nombra a ninguna», ver
`cardWalk`— llevada a la URL: si veintiséis botones apuntan al mismo `/redirigir`, ese destino es la ACCIÓN de
la página, no un anuncio.

MEDIDO el 2026-08-26 sobre las páginas que condujeron las rondas:

    ficha real (autoscout24)   : 2 anclas por ruta — min 2, max 2, mediana 2
    «IR A LA OFERTA» (kelisto) : /redirigir       ×26
    política de privacidad     : /privacy-policy  ×297
    enlace a la propia página  : /internet-movil  ×2083

Ese hueco es lo que hace legítimo el corte: **8** está cuatro veces por encima de una ficha real y tres por
debajo de la basura observada — la misma forma de elegir umbral que V2-323 (2× frente a 11,5× y 0,2×).

Sin él entraban en la hoja «IR A LA OFERTA — 27,90 €» y «Mostrar detalles» (que apunta a `#`), junto a avisos
legales sin título: los «datos basura (disclaimers)» que el juez nombró en `best-rated-rental-car__es`
(mecanismo 1) y la fila-botón ya vista en coches.net («Buen precio — 9.450 €») y en kayak.

⚠️ NO ES UNA LISTA DE TEXTOS, que es lo que se rechazó en V2-324: el texto del botón lo inventa cada sitio,
pero «esta URL la comparten veintiséis anclas» es un hecho de la página.

Comprobado en vivo, misma página y mismo instante: en el comparador las dos filas-botón desaparecen; en el
marketplace la extracción sale IDÉNTICA (20 filas, 13 con nombre).

Y HAY UN EFECTO QUE NO ESPERABA, visible en el fixture de abajo: al cortar los botones compartidos, `cands`
queda vacío y entra el RECOLECTOR SIN ANCLAS (V2-320-A), que sube desde el precio y encuentra los nombres
reales. El corte no solo quita basura — desbloquea la maquinaria que ya existía. Sin él, una página de diez
ofertas colapsa en UNA fila llamada «IR A LA OFERTA», porque las diez comparten destino y el dedup las funde.

⚠️ EL FIXTURE COSTÓ TRES INTENTOS, y las tres formas de no reproducir quedan aquí para el siguiente:
  · `set_content` sin `<base href>` deja las URLs relativas SIN origen: `new URL()` falla, el dedup no funde
    nada y el corte no puede dispararse. El test pasaba con y sin el arreglo.
  · con el botón DENTRO del mismo `<article>` que la ficha, `cardPrice` (que exige `maxPaths=1`) no sube y el
    botón se queda sin precio, así que lo descarta la regla de siempre antes de llegar al corte.
  · la forma que SÍ reproduce es la medida: el botón en su propio bloque, con el precio al lado.
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


def _oferta(i: int) -> str:
    """La forma MEDIDA en un comparador: el nombre en un encabezado sin enlace, y el botón —que apunta al
    destino compartido— en su propio bloque con el precio al lado."""
    return (f'<article><h3>Fibra 600 Mb operador {i}</h3>'
            f'<div class="cta"><span>{25 + i},90 €</span>'
            f'<a href="/redirigir?to={i}">IR A LA OFERTA</a></div></article>')


_COMPARADOR = ('<html><head><base href="https://ejemplo.test/"></head><body>'
               + "".join(_oferta(i) for i in range(10)) + "</body></html>")


def _filas(page, html):
    page.set_content(html)
    return page.evaluate(dom._JS_EXTRACT, 30)


def test_el_boton_COMPARTIDO_no_entra(page):
    filas = _filas(page, _COMPARADOR)
    assert not any("IR A LA OFERTA" in str(f.get("title") or "") for f in filas), \
        [f.get("title") for f in filas]


def test_y_APARECEN_las_ofertas_reales_que_el_boton_tapaba(page):
    """El efecto que no esperaba: sin los botones, `cands` queda vacío y entra el recolector sin anclas, que
    saca los nombres. Sin el corte, las diez ofertas colapsan en UNA fila basura."""
    filas = _filas(page, _COMPARADOR)
    nombres = [str(f.get("title") or "") for f in filas]
    assert sum(1 for n in nombres if n.startswith("Fibra 600 Mb")) >= 8, nombres


def test_una_ficha_con_DOS_anclas_sobrevive_CON_SU_ENLACE(page):
    """Medido: un marketplace real da exactamente 2 anclas por ficha (foto y título), y el umbral es 8 para que
    ese caso no roce el corte.

    ⚠️ Se comprueba el ENLACE y no solo el nombre, y eso lo enseñó el desarme: con un umbral demasiado bajo las
    fichas SÍ se cortan, pero entonces `cands` queda vacío y el recolector sin anclas las rescata por el
    precio… **sin url**, porque ese camino no la tiene (su propio contrato lo dice). O sea que el coste de
    pasarse no es perder la fila: es perder la forma de ACTUAR sobre ella, que es justo lo que V2-240 exige de
    un resultado. Una aserción sobre el título habría pasado con el umbral en 1."""
    html = ('<html><head><base href="https://ejemplo.test/"></head><body>' + "".join(
        f'<article><a href="/anuncios/coche-{i}"><img></a>'
        f'<a href="/anuncios/coche-{i}"><h3>Skoda Octavia {i}</h3></a>'
        f'<span>{3990 + i} €</span></article>' for i in range(6)) + "</body></html>")
    filas = _filas(page, html)
    skodas = [f for f in filas if str(f.get("title") or "").startswith("Skoda")]
    assert len(skodas) >= 5, [f.get("title") for f in filas]
    assert all(str(f.get("url") or "").endswith(tuple(f"/anuncios/coche-{i}" for i in range(6)))
               for f in skodas), "las fichas perdieron su enlace: el corte se pasó de agresivo"


def test_TRES_anclas_al_mismo_anuncio_tampoco_se_cortan(page):
    """Sensibilidad por el otro lado: foto, título y vendedor apuntando al mismo anuncio son normales."""
    html = ('<html><head><base href="https://ejemplo.test/"></head><body><article>'
            '<a href="/anuncios/uno"><img></a><a href="/anuncios/uno"><h3>Audi A3 Sportback</h3></a>'
            '<a href="/anuncios/uno">ver vendedor</a><span>11.990 €</span></article></body></html>')
    assert any("Audi A3" in str(f.get("title") or "") for f in _filas(page, html))
