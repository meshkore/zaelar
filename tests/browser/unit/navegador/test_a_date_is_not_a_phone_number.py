"""V2-321 — una FECHA no es un número al que llamar, y confundirlas ascendía el mobiliario a la cabecera.

`telText` decía descartar las fechas «porque la barra no es separador aquí». Eso cubre `25/08/2026` y NO cubre
`2026-08-25`, que es el formato ISO y el que las páginas escriben de verdad: diez dígitos con guiones y un
espacio — los tres separadores que el predicado admite.

MEDIDO EN VIVO (2026-08-25, `best-rated-rental-car__es` contra kayak.es). Las tres filas de mobiliario del pie
salieron de la extracción con `tel: "2026-08-25 12"`:

    «Inicio»                                          tel 2026-08-25 12
    «Echa un vistazo a nuestras preguntas frecuentes» tel 2026-08-25 12
    «Envíanos un comentario»                          tel 2026-08-25 12

Y EL DAÑO NO ES LA FILA DE MÁS. `act_api.by_amount` reparte la hoja por lo ACCIONABLE —un importe **o un
número al que llamar**— así que un teléfono falso ASCIENDE esas tres al principio; el top-5 que
`live_blocks._sheet_top_rows` le pasa al cerebro pasó a ser portada, FAQ y feedback; el cerebro se negó a
ofrecer eso, con toda la razón; y el juez puntuó `compare-insurance-quotes__es` con «negó tener resultados que
el sistema le había entregado». Seis saltos desde una línea, y en el sexto la culpa parecía del modelo.

Se prueba RENDERIZANDO, como el resto de la extracción: un test de fuente daría por bueno un regex que
compila, y lo que importa es lo que sale de un DOM de verdad.
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


# ── lo que el arreglo tiene que SEGUIR encontrando ────────────────────────────────────────────────────────
# Es la mitad que importa: en un directorio de fontaneros o peluquerías el teléfono ES el dato que resuelve el
# encargo (V2-240), y una fila sin importe y sin teléfono se descarta entera (`if(!price && !tel) continue`).
# Un falso negativo aquí no ensucia la hoja: la vacía.
@pytest.mark.parametrize("texto,esperado", [
    ("Fontanería Paco · 600 123 456", "600 123 456"),
    ("Llámanos: +34 91 123 45 67", "+34 91 123 45 67"),
    ("Tel. 600-123-456", "600-123-456"),
    ("Contacto 91.123.45.67", "91.123.45.67"),
    ("Móvil 34 600 111 222", "34 600 111 222"),
])
def test_un_telefono_de_verdad_sigue_saliendo(page, texto, esperado):
    assert _tel(page, texto) == esperado


# ── y lo que NO puede volver a colarse ────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("texto", [
    "Actualizado 2026-08-25 12:04",     # el caso MEDIDO, verbatim de kayak.es
    "Publicado el 2026-08-25",          # ISO a secas
    "Válido hasta 31-12-2026",          # europeo con guiones
    "Fecha 25.08.2026",                 # europeo con puntos
])
def test_una_fecha_no_es_un_telefono(page, texto):
    assert _tel(page, texto) == ""


@pytest.mark.parametrize("texto", [
    "Precio 1.234,56 €",                # un importe: seis dígitos, ya lo descartaba
    "Ref 9788412345678",                # código de barras: sin separadores, ya lo descartaba
])
def test_lo_que_ya_se_descartaba_sigue_descartándose(page, texto):
    """Sensibilidad de las dos exclusiones viejas: el arreglo añade una tercera, no sustituye a las otras."""
    assert _tel(page, texto) == ""


def test_el_caso_COMPLETO_el_pie_de_pagina_deja_de_producir_filas(page):
    """De punta a punta y con la forma real: sin importe y sin teléfono, la regla que YA existía
    (`if(!price && !tel) continue`) descarta el mobiliario sola. No hace falta ninguna lista negra de textos —
    que es lo que el operador rechaza desde `no_hardcoded_understand`: el criterio es estructural."""
    page.set_content(
        '<html><body><div class="footer">'
        '<div class="col"><a href="/">Inicio</a><span>Actualizado 2026-08-25 12:04</span></div>'
        '<div class="col"><a href="/help/faq">Preguntas frecuentes</a><span>Actualizado 2026-08-25 12:04</span></div>'
        '<div class="col"><a href="/feedback">Envíanos un comentario</a><span>Actualizado 2026-08-25 12:04</span></div>'
        '</div></body></html>')
    assert page.evaluate(dom._JS_EXTRACT, 20) == []


def test_y_una_ficha_REAL_junto_a_una_fecha_no_se_pierde(page):
    """El riesgo del arreglo por el otro lado: una ficha legítima que casualmente tiene una fecha al lado sigue
    saliendo, porque lo que la salva es su IMPORTE y el corte de fecha solo mira al candidato a teléfono."""
    page.set_content(
        '<html><body><div class="c"><a href="/deal/1">Alquiler Coche Málaga</a>'
        '<span>105 €</span><span>Actualizado 2026-08-25 12:04</span></div></body></html>')
    rows = page.evaluate(dom._JS_EXTRACT, 5)
    assert rows and rows[0]["title"].startswith("Alquiler Coche")
    assert rows[0]["price"]
    assert not rows[0]["tel"]
