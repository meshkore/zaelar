"""Lo que NO es un número al que llamar — y confundirlo ascendía el mobiliario a la cabecera de la hoja.

Dos formas medidas el mismo día, y la segunda salió de verificar el ARREGLO de la primera contra el caso real
en vez de contra su propio test: V2-321 era correcto y quedaba corto.

## V2-321 — una FECHA no es un teléfono

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


# ── V2-322 · un teléfono no cruza un SALTO DE LÍNEA ───────────────────────────────────────────────────────
# El separador era `[\s.\-]`, y `\s` incluye `\n`: dos números de DOS NODOS DISTINTOS, que `innerText` pega en
# la frontera de bloque, se leían como uno solo.
#
# MEDIDO EN VIVO contra `autoscout24.es/lst/cit_madrid/ft_diesel?…` (2026-08-25 18:53, `search-buy-used-car__es`,
# reproducido con la URL exacta que usó el worker): de una página llena de coches reales salieron TRES filas, y
# dos eran «Página de inicio» y «Buscar» con `tel: "2020\n360.000"` — el AÑO de un anuncio y su KILOMETRAJE.
#
# Ninguna regla de FORMA lo cazaba, y esa es la lección: tomada como una sola cadena, `2020\n360.000` no se
# parece a nada sospechoso —diez dígitos, separadores válidos—. Solo es absurda cuando se sabe que son dos datos
# distintos, y lo único que lo dice es el salto de línea.
#
# El veredicto del juez fue «la hoja se llenó con elementos de interfaz de autoscout24», con V2-321 ya dentro.
# O sea que la verificación que encontró esto no fue el test unitario del arreglo —que pasaba— sino volver a
# medir EL CASO.

def _tel_en_dos_bloques(page, izq: str, der: str) -> str:
    """El salto NO se escribe: lo produce `innerText` en la frontera de dos BLOQUES, que es exactamente como
    aparece en la página real. Un `\n` dentro de un `<span>` lo colapsa el HTML a un espacio y no reproduce
    nada — el primer intento de este test cayó justo ahí, y el fixture que no reproduce da un rojo que no es."""
    page.set_content(
        f'<html><body><div class="c"><a href="/f/1">Ficha</a>'
        f'<div>{izq}</div><div>{der}</div></div></body></html>')
    rows = page.evaluate(dom._JS_EXTRACT, 5)
    return str((rows[0].get("tel") if rows else "") or "")


@pytest.mark.parametrize("izq,der", [
    ("2020", "360.000"),        # el caso MEDIDO: año y kilometraje de un anuncio de autoscout24
    ("2018", "120.500 km"),
    ("45.000", "90.000"),       # dos precios de dos fichas contiguas
])
def test_dos_numeros_de_dos_nodos_no_son_un_telefono(page, izq, der):
    assert _tel_en_dos_bloques(page, izq, der) == ""


def test_y_ANTES_del_arreglo_ese_fixture_SI_producia_un_telefono():
    """La sensibilidad del de arriba, sobre el predicado viejo: sin esto, un fixture que no reproduce dejaría
    el test en verde para siempre sin haber medido nada."""
    import re
    viejo = re.compile(r"(?:\+\d{1,3}[\s.\-]?)?(?:\d[\s.\-]?){8,14}")
    m = viejo.search("2020\n360.000")
    assert m and len(re.sub(r"\D", "", m.group(0))) >= 9


def test_el_COSTE_de_esta_regla_esta_ASUMIDO_no_olvidado(page):
    """Un teléfono REAL partido por un salto deja de reconocerse. Se asume, y se escribe aquí para que sea una
    DECISIÓN y no un descuido: el camino primario es `a[href^="tel:"]` —inequívoco, sin tocar— y el texto es el
    respaldo; el coste medido del falso positivo es una ronda entera envenenada, y un número que se rompe entre
    dos bloques es raro (los teléfonos viven dentro de un mismo elemento en línea).

    Si algún día un directorio real pierde teléfonos por esto, ESTE es el test que hay que venir a discutir."""
    assert _tel_en_dos_bloques(page, "600 123", "456") == ""


def test_el_mismo_numero_en_UNA_linea_sigue_saliendo(page):
    """La sensibilidad de la de arriba: lo que se pierde es el salto, no el número."""
    assert _tel(page, "600 123 456") == "600 123 456"


# ── V2-326 · un SUPERÍNDICE no es parte del número ────────────────────────────────────────────────────────
# `cardPrice` lee `textContent`, que pega TODOS los descendientes. Las fichas cuelgan del precio una llamada a
# nota al pie en `<sup>`, así que el importe salía con un dígito de más.
#
# MEDIDO en autoscout24 (2026-08-25). Las hojas del DOM de la primera ficha:
#     [13] <SPAN> '€ 399'
#     [14] <SUP class="CurrentPrice_superscript__…"> '1'
# → extraído `€ 3991`. Un error de MAGNITUD (×10) justo en el dato sobre el que se compara.
#
# ⚠️ NO se arregla saltando los nodos con hijos, que es lo primero que parece: la lectura por ancestros existe a
# propósito, porque hay precios que solo viven en el PADRE (`<div>€ <span>399</span></div>`). Lo que sobra es el
# superíndice, así que es el superíndice lo que se quita.

def _precio(page, html: str) -> str:
    page.set_content(f"<html><body>{html}</body></html>")
    filas = page.evaluate(dom._JS_EXTRACT, 5)
    return str((filas[0].get("price") if filas else "") or "")


def test_la_nota_al_pie_no_se_pega_al_importe(page):
    """El caso MEDIDO, con la forma real de la ficha."""
    assert _precio(page, '<article><a href="/anuncios/x-1">Skoda Octavia</a>'
                         '<div><span>€ 399</span><sup>1</sup></div></article>') == "€ 399"


def test_un_precio_que_solo_vive_en_el_PADRE_sigue_saliendo(page):
    """La razón por la que NO se saltan los nodos con hijos. Si esto se rompe, el arreglo eligió el atajo."""
    assert _precio(page, '<article><a href="/anuncios/x-2">Audi A3</a>'
                         '<div>€ <span>453</span></div></article>') == "€ 453"


def test_un_precio_normal_no_se_toca(page):
    assert _precio(page, '<article><a href="/anuncios/x-3">Citroen C3</a>'
                         '<span>2.900 €</span></article>') == "2.900 €"


def test_el_COSTE_de_esta_regla_esta_ASUMIDO_no_olvidado_tambien_aqui(page):
    """Hay sitios que ponen los CÉNTIMOS en superíndice y ahí se pierden. Se asume porque los dos errores no son
    comparables: magnitud (×10) frente a redondeo (0,25 %). Y va en la dirección que este fichero ya eligió —
    «no se reconstruye el separador decimal… adivinar mal ahí cambia un precio por cien».

    Si algún día un catálogo pierde céntimos por esto, ESTE es el test que hay que venir a discutir."""
    assert _precio(page, '<article><a href="/anuncios/x-4">Dacia Sandero</a>'
                         '<div><span>€ 399</span><sup>99</sup></div></article>') == "€ 399"
