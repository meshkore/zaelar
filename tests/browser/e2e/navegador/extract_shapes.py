"""El extractor contra las FORMAS reales de un listado, en un navegador de verdad (V2-235).

POR QUÉ RENDERIZA: `_JS_EXTRACT` corre dentro de la página y lee `innerText`, que **no es el HTML**. El fallo
que este fichero fija solo existe cuando el navegador compone el texto: un precio partido en varios `<span>`
—entero, coma, céntimos, símbolo— más una copia del importe en un nodo fuera de pantalla. Leyendo el fuente del
selector no se ve; ejecutándolo, sale a la primera.

Lo medido por el arnés (2026-08-21, `cheapest-monitor`), notas crudas que llegaron al cerebro:

    «169 — 00 € — .../LG-27US500-W-.../dp/B0DH51BPZD»      → era 169,00 €
    «284 — 87 € — .../Dell-Plus-Monitor-.../dp/B0F29RH4RY» → era 284,87 €

Dos averías en la misma fila, y ninguna es del modelo — zaelar reconstruyó «LG 27US500-W 4K por 169 €» sacando
el modelo DE LA URL, que es lo correcto con lo poco que le dimos:

  1. **la COMA faltaba de la clase de caracteres del precio** (`[\\d.]`, solo punto de millares), así que sobre
     «169,00 €» el patrón empezaba a casar en «00» → «00 €». Un monitor de 169 € anunciado como de 0 €.
  2. **el NOMBRE no estaba en el enlace del precio.** En una rejilla el importe vive en su propio `<a>` y el
     nombre en el encabezado de la tarjeta, así que el enlace que trae el precio no tiene nombre dentro.

El arreglo del nombre es estructural y no nombra ningún sitio: **un listado es una rejilla de TARJETAS y el
nombre de cada cosa es el encabezado de su tarjeta**. Vale para un producto, un piso, un hotel o una entrada.
Con dos frenos, los dos probados aquí abajo: se sube como mucho cinco niveles, y se para en cuanto el ancestro
deja de ser una tarjeta y pasa a ser la rejilla — si no, el «Resultados» de la sección nombraría a todas las
filas, y un nombre que vale para todo no nombra nada.

Run:  ./.venv/bin/python tests/browser/e2e/navegador/extract_shapes.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, ENGINE)

from widgets.navegador.dom import _JS_EXTRACT  # noqa: E402

# ── las formas ───────────────────────────────────────────────────────────────────────────────────────────────

# 1 · precio partido en spans + importe repetido fuera de pantalla, y el nombre en el h2 de la tarjeta.
PARTIDO = """<div data-component-type="s-search-result">
  <h2><a href="https://tienda.invalid/LG-27US500-W/dp/B0DH51BPZD">LG 27US500-W Monitor 27" 4K UHD IPS</a></h2>
  <a class="p" href="https://tienda.invalid/LG-27US500-W/dp/B0DH51BPZD">
    <span><span class="off">169,00&nbsp;€</span><span aria-hidden="true"><span>€</span><span>169<span>,</span></span><span>00</span></span></span>
  </a></div>"""

# 2 · el enlace SÍ lleva el nombre dentro (la forma clásica: Wallapop, Idealista).
CLASICA = """<div class="card"><a href="https://otra.invalid/item/12345">
  <img alt="" src="/x.jpg"><div>Silla de oficina ergonómica</div><div>129 €</div></a></div>"""

# 3 · la trampa: la tarjeta NO tiene encabezado, pero la SECCIÓN sí. Nadie puede llamarse «Resultados».
SIN_NOMBRE = """<section><h1>Resultados de la búsqueda</h1>
  <ul>
    <li><a href="https://gris.invalid/p/aaa"><span>75,50 €</span></a></li>
    <li><a href="https://gris.invalid/p/bbb"><span>81,00 €</span></a></li>
    <li><a href="https://gris.invalid/p/ccc"><span>99,90 €</span></a></li>
    <li><a href="https://gris.invalid/p/ddd"><span>12,00 €</span></a></li>
    <li><a href="https://gris.invalid/p/eee"><span>44,00 €</span></a></li>
  </ul></section>"""

# 4 · miles y decimales juntos, que es donde un patrón mal puesto se lleva el orden de magnitud por delante.
MILES = """<div class="card"><h3><a href="https://coches.invalid/anuncio/9">Peugeot 407 SW 2.0 HDi</a></h3>
  <a href="https://coches.invalid/anuncio/9"><span>3.500,00 €</span></a></div>"""

# 5 · el entero y los céntimos en LÍNEAS distintas (sin copia fuera de pantalla). Aquí «169» es una línea
# propia, así que sin exigir una letra pasaba por NOMBRE del monitor — es literalmente el «169 — 00 € — …» que
# el arnés leyó en la nota cruda.
PARTIDO_EN_LINEAS = """<div class="card"><h3><a href="https://otra2.invalid/p/mon">Monitor Alurin CoreVision 24"</a></h3>
  <a href="https://otra2.invalid/p/mon"><div>169</div><div>00 €</div></a></div>"""

# ── V2-240: un resultado es un NOMBRE y una forma de ACTUAR, no un precio ───────────────────────────────────
# El filtro exigía precio porque «un anuncio tiene precio». Eso es verdad de UNA clase de encargo —la compra— y
# de ninguna otra: un fontanero, un barbero o un cerrajero no publican precio. Medido por el arnés:
# `best-plumber-same-day` y `weekend-barber`, los dos 1/5, con **0 filas extraídas** y el turno quedándose con lo
# único que le llegaba, el enlace del directorio. La forma de abajo es la de cualquier directorio de servicios.

# 6 · fichas de negocio SIN precio, con el teléfono en un `tel:` (la forma de las páginas amarillas de cualquier país).
SERVICIOS = """<div class="res"><h3><a href="https://guia.invalid/fontaneros/madrid/aqua-24h">Fontanería Aqua 24h</a></h3>
  <p>Urgencias 24 horas · Centro</p><a class="t" href="tel:+34910123456">910 12 34 56</a></div>
<div class="res"><h3><a href="https://guia.invalid/fontaneros/madrid/reparalia">Reparalia Fontaneros</a></h3>
  <p>Desatascos y fugas</p><a class="t" href="tel:+34915559988">915 55 99 88</a></div>"""

# 7 · el mismo caso pero el teléfono es TEXTO dentro de la tarjeta, sin `tel:` (más común de lo que parece).
SERVICIOS_TEXTO = """<div class="res"><h3><a href="https://guia2.invalid/b/barberia-lolo">Barbería Lolo</a></h3>
  <p>Abierto sábados · Tel. 622 41 88 03</p></div>"""

# 8 · la dirección CONTRARIA: sin precio y sin número no hay ficha. Si esto pasa, el arreglo convierte el menú
# de navegación de cualquier página en «resultados» y el extractor deja de servir para nada.
SOLO_NAVEGACION = """<nav><a href="https://guia.invalid/madrid">Madrid</a>
  <a href="https://guia.invalid/barcelona">Barcelona</a>
  <a href="https://guia.invalid/quienes-somos">Quiénes somos</a></nav>"""

# 9 · un código de barras y una fecha no son un teléfono (lo que se cuela si se cuenta dígitos y ya está).
FALSOS_NUMEROS = """<div class="card"><h3><a href="https://tienda.invalid/p/ean">Cable HDMI 2.1</a></h3>
  <p>EAN 8412345678905 · publicado 21/08/2026</p></div>"""

# ── V2-2xx: a LABEL is not a NAME (measured 2026-08-23, `cheapest-monitor`) ─────────────────────────────────
# The round delivered «MSI PRO MP273U — 164 €» and no extraction ever paired that name with that price. What the
# browser really returned, verbatim from the report:
#
#     {"title": "Nuevos (26) desde", "price": "164,00€", "url": ".../gp/offer-listing/B0DJ9KZG6P/..."}
#     {"title": "Mediano:",          "price": "379,99 €"}
#
# Eight of the thirteen rows on the sheet were called «Recomendado:», «Mediano:» (four times) or «Más bajo:» —
# the captions of a carousel, sitting where a monitor's name belongs. Two independent faults:
#   · Amazon's product URL is `/dp/<ASIN>`, which `ITEM` did not know, so NOTHING scored as a real listing and
#     the fallback handed back every price-bearing link on the page, chrome included;
#   · a caption that introduces a price was accepted as the thing's name.

# 10 · the offers box and a carousel caption, next to a REAL product link. This is the shape that produced the
# «164,00€ with no name» row: the offer-listing link carries the price, the caption carries the words.
AMAZON_CHROME = """<div class="s-result"><h2><a href="https://tienda.invalid/MSI-PRO-MP273U/dp/B0DJ9KZG6P">MSI PRO MP273U 27" 4K</a></h2>
  <a href="https://tienda.invalid/MSI-PRO-MP273U/dp/B0DJ9KZG6P"><span>164,00&nbsp;€</span></a></div>
<div class="offers"><a href="https://tienda.invalid/gp/offer-listing/B0DJ9KZG6P/ref=dp_olp_NEW_mbc">
  <div>Nuevos (26) desde</div><div>164,00&nbsp;€</div></a></div>
<div class="carousel">
  <a href="https://tienda.invalid/sspa/aaa"><div>Mediano:</div><div>379,99 €</div></a>
  <a href="https://tienda.invalid/sspa/bbb"><div>Mediano:</div><div>289,99 €</div></a>
  <a href="https://tienda.invalid/sspa/ccc"><div>Recomendado:</div><div>297,99 €</div></a></div>"""

# 11 · the caption WITHOUT any real product link on the page — the fallback branch, where `cands` is handed back
# whole. A caption must not become a name there either, and blanking it must not delete the ROW: the price and
# the link are real and the brain can still describe it by its link.
# Distinct PATHS on purpose: the dedup key is origin+pathname, so two sponsored links differing only in their
# query collapse into one row — correct, and not what this shape is about. A real carousel points at real
# products, and the caption repeating across them is exactly the second tell.
SOLO_CROMO = """<div class="carousel">
  <a href="https://tienda.invalid/sspa/aaa"><div>Mediano:</div><div>379,99 €</div></a>
  <a href="https://tienda.invalid/sspa/bbb"><div>Mediano:</div><div>289,99 €</div></a></div>"""

fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def extract(page, body):
    page.set_content("<!doctype html><meta charset=utf-8><body>" + body + "</body>")
    return page.evaluate(_JS_EXTRACT, 14)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()

        # ── 1 · el precio partido ──
        got = extract(page, PARTIDO)
        check("1 · una fila por ficha", len(got) == 1, str(got))
        if got:
            check("1a · el precio se lee ENTERO, con sus céntimos",
                  got[0]["price"].startswith("169,00"), f"price={got[0]['price']!r} (era «00 €»)")
            check("1b · el nombre sale del encabezado de la tarjeta",
                  got[0]["title"].startswith("LG 27US500-W"), f"title={got[0]['title']!r} (era «»)")

        # ── 2 · la forma clásica no cambia ──
        got = extract(page, CLASICA)
        check("2 · con el nombre DENTRO del enlace, se sigue cogiendo de ahí",
              len(got) == 1 and got[0]["title"] == "Silla de oficina ergonómica" and got[0]["price"] == "129 €",
              str(got))

        # ── 3 · la trampa de la rejilla ──
        got = extract(page, SIN_NOMBRE)
        check("3 · cinco fichas, cinco filas", len(got) == 5, str(len(got)))
        malos = [i for i in got if "Resultados" in (i.get("title") or "")]
        check("3a · el encabezado de la SECCIÓN no nombra a nadie",
              not malos, f"{len(malos)} filas llamadas «Resultados de la búsqueda»")
        check("3b · sin nombre se queda SIN nombre, no se inventa",
              all(not (i.get("title") or "") for i in got), str([i.get("title") for i in got]))

        # ── 5 · el entero y los céntimos en líneas distintas ──
        got = extract(page, PARTIDO_EN_LINEAS)
        check("5 · un trozo de precio NO pasa por nombre",
              len(got) == 1 and not (got[0]["title"] or "").strip().isdigit(),
              f"title={got and got[0]['title']!r} — «169» no es el nombre de nada")
        if got:
            check("5a · el nombre sale de la tarjeta y el importe no se pierde",
                  got[0]["title"].startswith("Monitor Alurin") and "169" in got[0]["price"],
                  str(got[0]))

        # ── 4 · miles y decimales ──
        got = extract(page, MILES)
        check("4 · «3.500,00 €» se lee entero (un patrón mal puesto se come el orden de magnitud)",
              len(got) == 1 and got[0]["price"].startswith("3.500,00"), str(got))
        if got:
            check("4a · y el nombre es el del anuncio",
                  got[0]["title"].startswith("Peugeot 407"), f"title={got[0]['title']!r}")

        # ── 6 · fichas de servicio con `tel:` ──
        got = extract(page, SERVICIOS)
        check("6 · un listado SIN precios devuelve fichas (antes: 0 filas)", len(got) == 2, str(got))
        if len(got) == 2:
            check("6a · con su nombre", got[0]["title"].startswith("Fontanería Aqua"), str(got[0]))
            check("6b · y con el número al que llamar", "910" in (got[0].get("tel") or ""), str(got[0]))
            check("6c · sin inventar un precio que la página no da",
                  all(not (i.get("price") or "") for i in got), str([i.get("price") for i in got]))

        # ── 7 · el teléfono en texto ──
        got = extract(page, SERVICIOS_TEXTO)
        check("7 · el teléfono en TEXTO también hace ficha",
              len(got) == 1 and "622" in (got[0].get("tel") or ""), str(got))

        # ── 8 · la dirección contraria ──
        got = extract(page, SOLO_NAVEGACION)
        check("8 · un menú de navegación NO son resultados", not got, str(got))

        # ── 9 · números que no son teléfonos ──
        got = extract(page, FALSOS_NUMEROS)
        check("9 · un EAN y una fecha no son un número al que llamar", not got, str(got))

        # ── 10 · a real listing next to the offers box and a carousel ──
        got = extract(page, AMAZON_CHROME)
        titles = [i.get("title") or "" for i in got]
        check("10 · «/dp/» scores as a real listing, so the chrome is discarded",
              len(got) == 1, f"{len(got)} filas: {titles}")
        if got:
            check("10a · and the row kept is the PRODUCT, with its price",
                  got[0]["title"].startswith("MSI PRO MP273U") and got[0]["price"].startswith("164,00"),
                  str(got[0]))
        check("10b · «Nuevos (26) desde» never reaches the sheet",
              not any("Nuevos" in t for t in titles), str(titles))
        check("10c · nor does a carousel caption",
              not any(t.rstrip().endswith(":") for t in titles), str(titles))

        # ── 11 · the same chrome with NO real listing to filter it out ──
        got = extract(page, SOLO_CROMO)
        titles = [i.get("title") or "" for i in got]
        check("11 · the rows survive (price and link are real)", len(got) == 2, str(got))
        check("11a · but a caption is not a name: blank, never guessed",
              all(not t for t in titles), str(titles))
        check("11b · and the price is still there to describe them by",
              all((i.get("price") or "") for i in got), str([i.get("price") for i in got]))

        browser.close()

    print()
    if fails:
        print(f"✗ {len(fails)} sin cumplir: {', '.join(fails)}")
        return 1
    print("✓ el extractor lee el precio entero y saca el nombre de la tarjeta sin inventarlo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
