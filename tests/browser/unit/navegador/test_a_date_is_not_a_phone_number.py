"""What is NOT a number to call — and confusing it promoted footer furniture to the top of the sheet.

Two forms measured on the same day, and the second came from checking the FIX for the first against the real case
instead of against its own test: V2-321 was correct but insufficient.

## V2-321 — a DATE is not a phone number

`telText` said to discard dates “because the slash is not a separator here.” That covers `25/08/2026` and does NOT cover
`2026-08-25`, which is the ISO format and the one pages actually write: ten digits with hyphens and a
space — the three separators the predicate allows.

MEASURED LIVE (2026-08-25, `best-rated-rental-car__es` against kayak.es). The three footer-furniture rows
came from extraction with `tel: "2026-08-25 12"`:

    «Inicio»                                          tel 2026-08-25 12
    «Echa un vistazo a nuestras preguntas frecuentes» tel 2026-08-25 12
    «Envíanos un comentario»                          tel 2026-08-25 12

AND THE DAMAGE IS NOT JUST ONE EXTRA ROW. `act_api.by_amount` distributes the sheet by what is ACTIONABLE —an amount **or a
number to call**— so a fake phone number PROMOTES those three to the top; the top five that
`live_blocks._sheet_top_rows` passes to the brain became homepage, FAQ, and feedback; the brain refused to
offer that, quite rightly; and the judge scored `compare-insurance-quotes__es` as “denied having results that
the system had delivered.” Six hops from one line, and at the sixth the blame appeared to lie with the model.

It is tested by RENDERING, like the rest of the extraction: a source test would approve a regex that
compiles, but what matters is what comes out of a real DOM.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

from widgets.navegador import dom

_HTML = '<html><body><div class="c"><a href="/f/1">Ficha</a><span>%s</span></div></body></html>'


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        p = browser.new_page()
        yield p
        browser.close()


def _tel(page, texto: str) -> str:
    page.set_content(_HTML % texto)
    rows = page.evaluate(dom._JS_EXTRACT, 5)
    return str((rows[0].get("tel") if rows else "") or "")


# ── what the fix must CONTINUE finding ────────────────────────────────────────────────────────
# This is the half that matters: in a plumbers’ or hairdressers’ directory, the phone number IS the data that fulfills the
# request (V2-240), and a row without an amount or phone number is discarded entirely (`if(!price && !tel) continue`).
# A false negative here does not pollute the sheet: it empties it.
@pytest.mark.parametrize("texto,esperado", [
    ("Fontanería Paco · 600 123 456", "600 123 456"),
    ("Llámanos: +34 91 123 45 67", "+34 91 123 45 67"),
    ("Tel. 600-123-456", "600-123-456"),
    ("Contacto 91.123.45.67", "91.123.45.67"),
    ("Móvil 34 600 111 222", "34 600 111 222"),
])
def test_un_telefono_de_verdad_sigue_saliendo(page, texto, esperado):
    assert _tel(page, texto) == esperado


# ── and what must NOT slip in again ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto", [
    "Actualizado 2026-08-25 12:04",     # the MEASURED case, verbatim from kayak.es
    "Publicado el 2026-08-25",          # ISO alone
    "Válido hasta 31-12-2026",          # European format with hyphens
    "Fecha 25.08.2026",                 # European format with dots
])
def test_una_fecha_no_es_un_telefono(page, texto):
    assert _tel(page, texto) == ""


@pytest.mark.parametrize("texto", [
    "Precio 1.234,56 €",                # an amount: six digits, already discarded
    "Ref 9788412345678",                # barcode: no separators, already discarded
])
def test_lo_que_ya_se_descartaba_sigue_descartándose(page, texto):
    """Sensitivity of the two old exclusions: the fix adds a third; it does not replace the others."""
    assert _tel(page, texto) == ""


def test_el_caso_COMPLETO_el_pie_de_pagina_deja_de_producir_filas(page):
    """End to end and in the real form: without an amount or phone number, the rule that ALREADY existed
    (`if(!price && !tel) continue`) discards the furniture by itself. No text blacklist is needed —
    which is what the operator rejects through `no_hardcoded_understand`: the criterion is structural."""
    page.set_content(
        '<html><body><div class="footer">'
        '<div class="col"><a href="/">Inicio</a><span>Actualizado 2026-08-25 12:04</span></div>'
        '<div class="col"><a href="/help/faq">Preguntas frecuentes</a><span>Actualizado 2026-08-25 12:04</span></div>'
        '<div class="col"><a href="/feedback">Envíanos un comentario</a><span>Actualizado 2026-08-25 12:04</span></div>'
        '</div></body></html>')
    assert page.evaluate(dom._JS_EXTRACT, 20) == []


def test_y_una_ficha_REAL_junto_a_una_fecha_no_se_pierde(page):
    """The risk of the fix in the other direction: a legitimate listing that happens to have a date beside it still
    appears, because its AMOUNT saves it and the date check only looks at the phone-number candidate."""
    page.set_content(
        '<html><body><div class="c"><a href="/deal/1">Alquiler Coche Málaga</a>'
        '<span>105 €</span><span>Actualizado 2026-08-25 12:04</span></div></body></html>')
    rows = page.evaluate(dom._JS_EXTRACT, 5)
    assert rows and rows[0]["title"].startswith("Alquiler Coche")
    assert rows[0]["price"]
    assert not rows[0]["tel"]


# ── V2-322 · a phone number does not cross a LINE BREAK ───────────────────────────────────────────────────────
# The separator was `[\s.\-]`, and `\s` includes `\n`: two numbers from TWO DISTINCT NODES, which `innerText` joins at
# the block boundary, were read as one.
#
# MEASURED LIVE against `autoscout24.es/lst/cit_madrid/ft_diesel?…` (2026-08-25 18:53, `search-buy-used-car__es`,
# reproduced with the exact URL used by the worker): a page full of real cars produced THREE rows, and
# two were “Home page” and “Search” with `tel: "2020\n360.000"` — the YEAR of an ad and its MILEAGE.
#
# No rule based on FORM caught it, and that is the lesson: treated as one string, `2020\n360.000` does not
# look suspicious —ten digits, valid separators—. It is absurd only when you know they are two distinct data points,
# and the only thing that tells you so is the line break.
#
# The judge’s verdict was “the sheet filled up with autoscout24 interface elements,” with V2-321 already included.
# In other words, the verification that found this was not the fix’s unit test —which passed— but re-measuring
# THE CASE.

def _tel_en_dos_bloques(page, izq: str, der: str) -> str:
    """The line break is NOT written directly: `innerText` produces it at the boundary of two BLOCKS, exactly as it
    appears on the real page. A `\n` inside a `<span>` is collapsed by HTML into a space and reproduces nothing
    — this test’s first attempt fell right there, and a fixture that does not reproduce the case gives a false failure."""
    page.set_content(
        f'<html><body><div class="c"><a href="/f/1">Ficha</a>'
        f'<div>{izq}</div><div>{der}</div></div></body></html>')
    rows = page.evaluate(dom._JS_EXTRACT, 5)
    return str((rows[0].get("tel") if rows else "") or "")


@pytest.mark.parametrize("izq,der", [
    ("2020", "360.000"),        # the MEASURED case: year and mileage of an autoscout24 ad
    ("2018", "120.500 km"),
    ("45.000", "90.000"),       # two prices from two adjacent listings
])
def test_dos_numeros_de_dos_nodos_no_son_un_telefono(page, izq, der):
    assert _tel_en_dos_bloques(page, izq, der) == ""


def test_y_ANTES_del_arreglo_ese_fixture_SI_producia_un_telefono():
    """Sensitivity of the test above, against the old predicate: without this, a fixture that does not reproduce the case
    would leave the test green forever without measuring anything."""
    import re
    viejo = re.compile(r"(?:\+\d{1,3}[\s.\-]?)?(?:\d[\s.\-]?){8,14}")
    m = viejo.search("2020\n360.000")
    assert m and len(re.sub(r"\D", "", m.group(0))) >= 9


def test_el_COSTE_de_esta_regla_esta_ASUMIDO_no_olvidado(page):
    """A REAL phone number split by a line break is no longer recognized. This is assumed and written here so it is a
    DECISION rather than an oversight: the primary path is `a[href^="tel:"]` —unambiguous and untouched— and text is the
    fallback; the measured cost of the false positive is an entire poisoned round, and a number split between
    two blocks is rare (phone numbers live inside the same inline element).

    If a real directory ever loses phone numbers because of this, THIS is the test to come discuss."""
    assert _tel_en_dos_bloques(page, "600 123", "456") == ""


def test_el_mismo_numero_en_UNA_linea_sigue_saliendo(page):
    """Sensitivity of the test above: what is lost is the line break, not the number."""
    assert _tel(page, "600 123 456") == "600 123 456"


# ── V2-326 · a SUPERSCRIPT is not part of the number ────────────────────────────────────────────────────────
# `cardPrice` reads `textContent`, which joins ALL descendants. Listings append a footnote marker to the price
# in `<sup>`, so the amount came out with one extra digit.
#
# MEASURED on autoscout24 (2026-08-25). The DOM leaves of the first listing:
#     [13] <SPAN> '€ 399'
#     [14] <SUP class="CurrentPrice_superscript__…"> '1'
# → extracted `€ 3991`. A MAGNITUDE error (×10) in exactly the data used for comparison.
#
# ⚠️ This is NOT fixed by skipping nodes with children, which is the first apparent solution: ancestor reading exists on
# purpose because some prices live only in the PARENT (`<div>€ <span>399</span></div>`). The superscript is the excess,
# so the superscript is what must be removed.

def _precio(page, html: str) -> str:
    page.set_content(f"<html><body>{html}</body></html>")
    filas = page.evaluate(dom._JS_EXTRACT, 5)
    return str((filas[0].get("price") if filas else "") or "")


def test_la_nota_al_pie_no_se_pega_al_importe(page):
    """The MEASURED case, in the listing’s real form."""
    assert _precio(page, '<article><a href="/anuncios/x-1">Skoda Octavia</a>'
                         '<div><span>€ 399</span><sup>1</sup></div></article>') == "€ 399"


def test_un_precio_que_solo_vive_en_el_PADRE_sigue_saliendo(page):
    """The reason nodes with children are NOT skipped. If this breaks, the fix chose the shortcut."""
    assert _precio(page, '<article><a href="/anuncios/x-2">Audi A3</a>'
                         '<div>€ <span>453</span></div></article>') == "€ 453"


def test_un_precio_normal_no_se_toca(page):
    assert _precio(page, '<article><a href="/anuncios/x-3">Citroen C3</a>'
                         '<span>2.900 €</span></article>') == "2.900 €"


def test_el_COSTE_de_esta_regla_esta_ASUMIDO_no_olvidado_tambien_aqui(page):
    """Some sites put the CENTS in superscript, and they are lost there. This is assumed because the two errors are not
    comparable: magnitude (×10) versus rounding (0.25%). And it follows the direction this file already chose —
    “the decimal separator is not reconstructed… guessing wrong there changes a price by a factor of one hundred.”

    If a catalog ever loses cents because of this, THIS is the test to come discuss."""
    assert _precio(page, '<article><a href="/anuncios/x-4">Dacia Sandero</a>'
                         '<div><span>€ 399</span><sup>99</sup></div></article>') == "€ 399"
