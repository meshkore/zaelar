"""V2-334 — a route shared by dozens of anchors is not the listing for anything.

This is the rule that this file already applies to the ANCESTOR —“data that names all of them names none of them,” see
`cardWalk`— applied to the URL: if twenty-six buttons point to the same `/redirigir`, that destination is the page's
ACTION, not a listing.

MEASURED on 2026-08-26 on the pages that drove the rounds:

    ficha real (autoscout24)   : 2 anclas por ruta — min 2, max 2, mediana 2
    «IR A LA OFERTA» (kelisto) : /redirigir       ×26
    política de privacidad     : /privacy-policy  ×297
    enlace a la propia página  : /internet-movil  ×2083

That gap is what makes the cutoff legitimate: **8** is four times above a real listing and three times below
the observed junk — the same way of choosing a threshold as V2-323 (2× versus 11.5× and 0.2×).

Without it, «IR A LA OFERTA — 27,90 €» and «Mostrar detalles» (which points to `#`) entered the sheet, along with
untitled legal notices: the «datos basura (disclaimers)» that the judge identified in `best-rated-rental-car__es`
(mechanism 1) and the button row already seen on coches.net («Buen precio — 9.450 €») and on kayak.

⚠️ THIS IS NOT A LIST OF TEXTS, which is what was rejected in V2-324: each site invents the button text,
but «this URL is shared by twenty-six anchors» is a fact about the page.

Verified live, on the same page and at the same instant: in the comparison site the two button rows disappear; in the
marketplace the extraction is IDENTICAL (20 rows, 13 with names).

AND THERE IS AN EFFECT I DID NOT EXPECT, visible in the fixture below: when the shared buttons are cut, `cands`
becomes empty and the ANCHORLESS COLLECTOR (V2-320-A) runs, moving up from the price and finding the real names.
The cutoff does not merely remove junk — it unlocks machinery that already existed. Without it, a page with ten
offers collapses into ONE row called «IR A LA OFERTA», because all ten share a destination and deduplication merges them.

⚠️ THE FIXTURE TOOK THREE ATTEMPTS, and the three ways not to reproduce it are left here for the next person:
  · `set_content` without `<base href>` leaves relative URLs WITHOUT an origin: `new URL()` fails, deduplication
    merges nothing, and the cutoff cannot trigger. The test passed both with and without the fix.
  · with the button INSIDE the same `<article>` as the listing, `cardPrice` (which requires `maxPaths=1`) does not
    move up and the button has no price, so the usual rule discards it before the cutoff is reached.
  · the form that DOES reproduce it is the measured one: the button in its own block, with the price beside it.
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
    """The MEASURED form on a comparison site: the name in an unlinked heading, and the button —which points to the
    shared destination— in its own block with the price beside it."""
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
    """The effect I did not expect: without the buttons, `cands` becomes empty and the anchorless collector runs,
    extracting the names. Without the cutoff, the ten offers collapse into ONE junk row."""
    filas = _filas(page, _COMPARADOR)
    nombres = [str(f.get("title") or "") for f in filas]
    assert sum(1 for n in nombres if n.startswith("Fibra 600 Mb")) >= 8, nombres


def test_una_ficha_con_DOS_anclas_sobrevive_CON_SU_ENLACE(page):
    """Measured: a real marketplace gives exactly 2 anchors per listing (photo and title), and the threshold is 8 so
    that case does not come close to the cutoff.

    ⚠️ The LINK is checked, not just the name, and the teardown demonstrated why: with a threshold that is too low the
    listings ARE cut, but then `cands` becomes empty and the anchorless collector rescues them from the
    price… **without a url**, because that path does not have one (its own contract says so). In other words, the cost
    of overshooting is not losing the row: it is losing the ability to ACT on it, which is exactly what V2-240 requires
    of a result. An assertion on the title would have passed with the threshold set to 1."""
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
    """Sensitivity in the other direction: photo, title, and seller pointing to the same listing are normal."""
    html = ('<html><head><base href="https://ejemplo.test/"></head><body><article>'
            '<a href="/anuncios/uno"><img></a><a href="/anuncios/uno"><h3>Audi A3 Sportback</h3></a>'
            '<a href="/anuncios/uno">ver vendedor</a><span>11.990 €</span></article></body></html>')
    assert any("Audi A3" in str(f.get("title") or "") for f in _filas(page, html))
