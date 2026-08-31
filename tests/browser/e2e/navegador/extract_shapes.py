"""The extractor against the real SHAPES of a listing, in a real browser (V2-235).

WHY IT RENDERS: `_JS_EXTRACT` runs inside the page and reads `innerText`, which **is not the HTML**. The bug
fixed by this file exists only when the browser composes the text: a price split across several `<span>` elements
—integer, comma, cents, symbol— plus a copy of the amount in an off-screen node. Reading the selector's source
does not reveal it; running it does, immediately.

Measured by the harness (2026-08-21, `cheapest-monitor`), raw notes that reached the brain:

    «169 — 00 € — .../LG-27US500-W-.../dp/B0DH51BPZD»      → era 169,00 €
    «284 — 87 € — .../Dell-Plus-Monitor-.../dp/B0F29RH4RY» → era 284,87 €

Two failures in the same row, and neither is in the model — zaelar reconstructed “LG 27US500-W 4K for €169” by
taking the model FROM THE URL, which is the right thing to do with the little information we gave it:

  1. **the COMMA was missing from the price character class** (`[\\d.]`, thousands separator only), so for
     “169,00 €” the pattern started matching at “00” → “00 €”. A €169 monitor advertised as costing €0.
  2. **the NAME was not in the price link.** In a grid the amount lives in its own `<a>` and the name in the
     card heading, so the link carrying the price has no name inside it.

The name fix is structural and does not name any site: **a listing is a grid of CARDS and each thing's name is
the heading of its card**. It works for a product, an apartment, a hotel, or a ticket. With two safeguards, both
tested below: it climbs at most five levels, and stops as soon as the ancestor ceases to be a card and becomes the
grid — otherwise the section's “Results” would name every row, and a name that applies to everything names nothing.

Run:  ./.venv/bin/python tests/browser/e2e/navegador/extract_shapes.py
"""
import os
import sys

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, ENGINE)

from widgets.navegador.dom import _JS_EXTRACT  # noqa: E402

# ── the shapes ───────────────────────────────────────────────────────────────────────────────────────────────

# 1 · price split across spans + amount repeated off-screen, and the name in the card's h2.
PARTIDO = """<div data-component-type="s-search-result">
  <h2><a href="https://tienda.invalid/LG-27US500-W/dp/B0DH51BPZD">LG 27US500-W Monitor 27" 4K UHD IPS</a></h2>
  <a class="p" href="https://tienda.invalid/LG-27US500-W/dp/B0DH51BPZD">
    <span><span class="off">169,00&nbsp;€</span><span aria-hidden="true"><span>€</span><span>169<span>,</span></span><span>00</span></span></span>
  </a></div>"""

# 2 · the link DOES contain the name (the classic shape: Wallapop, Idealista).
CLASICA = """<div class="card"><a href="https://otra.invalid/item/12345">
  <img alt="" src="/x.jpg"><div>Silla de oficina ergonómica</div><div>129 €</div></a></div>"""

# 3 · the trap: the card has NO heading, but the SECTION does. Nobody can be called “Results”.
SIN_NOMBRE = """<section><h1>Resultados de la búsqueda</h1>
  <ul>
    <li><a href="https://gris.invalid/p/aaa"><span>75,50 €</span></a></li>
    <li><a href="https://gris.invalid/p/bbb"><span>81,00 €</span></a></li>
    <li><a href="https://gris.invalid/p/ccc"><span>99,90 €</span></a></li>
    <li><a href="https://gris.invalid/p/ddd"><span>12,00 €</span></a></li>
    <li><a href="https://gris.invalid/p/eee"><span>44,00 €</span></a></li>
  </ul></section>"""

# 4 · thousands and decimals together, where a misplaced pattern loses the order of magnitude.
MILES = """<div class="card"><h3><a href="https://coches.invalid/anuncio/9">Peugeot 407 SW 2.0 HDi</a></h3>
  <a href="https://coches.invalid/anuncio/9"><span>3.500,00 €</span></a></div>"""

# 5 · the integer and cents on separate LINES (without an off-screen copy). Here “169” is its own line,
# so without requiring a letter it passed as the monitor's NAME — it is literally the “169 — 00 € — …” that
# the harness read in the raw note.
PARTIDO_EN_LINEAS = """<div class="card"><h3><a href="https://otra2.invalid/p/mon">Monitor Alurin CoreVision 24"</a></h3>
  <a href="https://otra2.invalid/p/mon"><div>169</div><div>00 €</div></a></div>"""

# ── V2-240: a result is a NAME and a way to ACT, not a price ───────────────────────────────────
# The filter required a price because “an ad has a price”. That is true of ONE kind of job —a purchase— and
# no other: a plumber, barber, or locksmith does not publish a price. Measured by the harness:
# `best-plumber-same-day` and `weekend-barber`, both 1/5, with **0 rows extracted** and the run retaining the only
# thing it received, the directory link. The shape below is that of any services directory.

# 6 · business listings WITHOUT a price, with the phone number in a `tel:` (the shape of yellow pages in any country).
SERVICIOS = """<div class="res"><h3><a href="https://guia.invalid/fontaneros/madrid/aqua-24h">Fontanería Aqua 24h</a></h3>
  <p>Urgencias 24 horas · Centro</p><a class="t" href="tel:+34910123456">910 12 34 56</a></div>
<div class="res"><h3><a href="https://guia.invalid/fontaneros/madrid/reparalia">Reparalia Fontaneros</a></h3>
  <p>Desatascos y fugas</p><a class="t" href="tel:+34915559988">915 55 99 88</a></div>"""

# 7 · the same case, but the phone number is TEXT inside the card, without `tel:` (more common than it seems).
SERVICIOS_TEXTO = """<div class="res"><h3><a href="https://guia2.invalid/b/barberia-lolo">Barbería Lolo</a></h3>
  <p>Abierto sábados · Tel. 622 41 88 03</p></div>"""

# 8 · the OPPOSITE direction: without a price and without a number there is no listing. If this happens, the fix
# turns any page's navigation menu into “results” and the extractor becomes useless.
SOLO_NAVEGACION = """<nav><a href="https://guia.invalid/madrid">Madrid</a>
  <a href="https://guia.invalid/barcelona">Barcelona</a>
  <a href="https://guia.invalid/quienes-somos">Quiénes somos</a></nav>"""

# 9 · a barcode and a date are not a phone number (what slips through if digits alone are counted).
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

# ── 12 · THE PRICE LIVES IN THE CARD, NOT IN THE LINK ────────────────────────────────────────────────────
# Verbatim from `es.wallapop.com/search?keywords=monitor`, measured 2026-08-23: 78 real listing anchors on
# screen and the extractor returned ZERO rows. Every listing is TWO anchors at the SAME item — one wrapping the
# photo, one wrapping the `<h3>` — and neither carries the price; it is a sibling inside the card. The
# price-or-phone gate therefore dropped all 78, which is the shape behind several rounds reporting “0 rows
# extracted” on second-hand marketplaces.
#
# Rendered rather than parsed, for the reason at the top of this file: the price is read off `innerText`, which
# is what the BROWSER composes, not the HTML. Two cards on purpose — one card alone cannot show that the walk
# stops before it reaches the neighbour's price.
TARJETA_CON_PRECIO_FUERA = """<div class="grid">
  <div class="card">
    <a href="https://2mano.invalid/item/lg-ultragear-1"><img src="x.jpg" alt="Monitor Gaming LG UltraGear 32GN600B"></a>
    <a href="https://2mano.invalid/item/lg-ultragear-1"><h3>Monitor Gaming LG UltraGear 32GN600B</h3></a>
    <div class="precio">150 €</div><div class="badge">Destacado</div>
  </div>
  <div class="card">
    <a href="https://2mano.invalid/item/samsung-22-2"><img src="y.jpg" alt="2 Monitores LG y Samsung 22 pulgadas"></a>
    <a href="https://2mano.invalid/item/samsung-22-2"><h3>2 Monitores LG y Samsung 22 pulgadas</h3></a>
    <div class="precio">50 €</div>
  </div></div>"""

# ── 13 · THE NEIGHBOUR'S PRICE ───────────────────────────────────────────────────────────────────────────
# The other half of 12, and the one that can really cause harm. A listing WITHOUT a published price next to one
# that has one: if the walk climbs to the grid, it brings back the amount from the one next to it. Measured while
# building 12 — with the margin used for the name and phone number (4 listings), BOTH rows came out as “24 50 €”,
# namely the neighbour's price AND misread (the cents group jumped from “Samsung 24” to “50 €”).
#
# A wrong name is visible; a wrong price reads like a discovery. So without its own price the listing is left out,
# as the V2-240 contract already says: a name and something to act on are required.
PRECIO_DE_LA_VECINA = """<div class="grid">
  <div class="card">
    <a href="https://2mano.invalid/item/sin-precio-1"><h3>Monitor sin precio publicado</h3></a>
    <div>Consultar</div>
  </div>
  <div class="card">
    <a href="https://2mano.invalid/item/con-precio-2"><h3>Monitor Samsung 24</h3></a>
    <div class="precio">50 €</div>
  </div></div>"""

# ── 14 · THE NAME AND PRICE IN THE SAME NODE ───────────────────────────────────────────────────────────
# The third way of fabricating a price, and the most expensive of the three. With the name and amount inside the
# same element —separated only by a `<br>`— the node's text is “Monitor Samsung 2450 €” with no separator,
# because `textContent` does not insert the line break that the browser RENDERS. Measured: without the length guard,
# a €50 monitor is returned as **€2450**, 49 times its price, with its correct name and link alongside it.
#
# The guard requires the node's text to be ALMOST ONLY the amount, so it finds no price here and the listing drops
# out — a real ad is lost, and that is the safe direction: one fewer row is noticeable, while an invented price
# with a real name and link is not.
NOMBRE_Y_PRECIO_JUNTOS = """<div class="card">
  <a href="https://2mano.invalid/item/samsung-24-9"><img src="x.jpg" alt="Monitor Samsung 24"></a>
  <div class="info">Monitor Samsung 24<br>50 €</div></div>"""

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

        # ── 1 · the split price ──
        got = extract(page, PARTIDO)
        check("1 · una fila por ficha", len(got) == 1, str(got))
        if got:
            check("1a · el precio se lee ENTERO, con sus céntimos",
                  got[0]["price"].startswith("169,00"), f"price={got[0]['price']!r} (era «00 €»)")
            check("1b · el nombre sale del encabezado de la tarjeta",
                  got[0]["title"].startswith("LG 27US500-W"), f"title={got[0]['title']!r} (era «»)")

        # ── 2 · the classic shape does not change ──
        got = extract(page, CLASICA)
        check("2 · con el nombre DENTRO del enlace, se sigue cogiendo de ahí",
              len(got) == 1 and got[0]["title"] == "Silla de oficina ergonómica" and got[0]["price"] == "129 €",
              str(got))

        # ── 3 · the grid trap ──
        got = extract(page, SIN_NOMBRE)
        check("3 · cinco fichas, cinco filas", len(got) == 5, str(len(got)))
        malos = [i for i in got if "Resultados" in (i.get("title") or "")]
        check("3a · el encabezado de la SECCIÓN no nombra a nadie",
              not malos, f"{len(malos)} filas llamadas «Resultados de la búsqueda»")
        check("3b · sin nombre se queda SIN nombre, no se inventa",
              all(not (i.get("title") or "") for i in got), str([i.get("title") for i in got]))

        # ── 5 · the integer and cents on separate lines ──
        got = extract(page, PARTIDO_EN_LINEAS)
        check("5 · un trozo de precio NO pasa por nombre",
              len(got) == 1 and not (got[0]["title"] or "").strip().isdigit(),
              f"title={got and got[0]['title']!r} — «169» no es el nombre de nada")
        if got:
            check("5a · el nombre sale de la tarjeta y el importe no se pierde",
                  got[0]["title"].startswith("Monitor Alurin") and "169" in got[0]["price"],
                  str(got[0]))

        # ── 4 · thousands and decimals ──
        got = extract(page, MILES)
        check("4 · «3.500,00 €» se lee entero (un patrón mal puesto se come el orden de magnitud)",
              len(got) == 1 and got[0]["price"].startswith("3.500,00"), str(got))
        if got:
            check("4a · y el nombre es el del anuncio",
                  got[0]["title"].startswith("Peugeot 407"), f"title={got[0]['title']!r}")

        # ── 6 · service listings with `tel:` ──
        got = extract(page, SERVICIOS)
        check("6 · un listado SIN precios devuelve fichas (antes: 0 filas)", len(got) == 2, str(got))
        if len(got) == 2:
            check("6a · con su nombre", got[0]["title"].startswith("Fontanería Aqua"), str(got[0]))
            check("6b · y con el número al que llamar", "910" in (got[0].get("tel") or ""), str(got[0]))
            check("6c · sin inventar un precio que la página no da",
                  all(not (i.get("price") or "") for i in got), str([i.get("price") for i in got]))

        # ── 7 · the phone number in text ──
        got = extract(page, SERVICIOS_TEXTO)
        check("7 · el teléfono en TEXTO también hace ficha",
              len(got) == 1 and "622" in (got[0].get("tel") or ""), str(got))

        # ── 8 · the opposite direction ──
        got = extract(page, SOLO_NAVEGACION)
        check("8 · un menú de navegación NO son resultados", not got, str(got))

        # ── 9 · numbers that are not phone numbers ──
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

        # ── 12 · the price lives in the CARD, not in the link ──
        got = extract(page, TARJETA_CON_PRECIO_FUERA)
        check("12 · dos fichas, dos filas (los dos enlaces de una ficha colapsan en una)", len(got) == 2, str(got))
        by_title = {(i.get("title") or ""): (i.get("price") or "") for i in got}
        check("12a · cada ficha se lleva SU precio, no el de la vecina",
              by_title.get("Monitor Gaming LG UltraGear 32GN600B") == "150 €"
              and by_title.get("2 Monitores LG y Samsung 22 pulgadas") == "50 €",
              str(by_title))
        check("12b · y conserva su nombre y su enlace",
              all((i.get("title") or "") and "/item/" in (i.get("url") or "") for i in got), str(got))

        # ── 13 · the neighbour's price ──
        got = extract(page, PRECIO_DE_LA_VECINA)
        check("13 · la ficha sin precio propio no se queda con el de al lado", len(got) == 1, str(got))
        if got:
            check("13a · y la que sí lo tiene conserva el SUYO, sin mezclar con el nombre",
                  got[0]["title"] == "Monitor Samsung 24" and got[0]["price"] == "50 €",
                  f"{got[0]['title']!r} / {got[0]['price']!r} (era «24 50 €» en las dos filas)")

        # ── 14 · the name and price in the same node ──
        got = extract(page, NOMBRE_Y_PRECIO_JUNTOS)
        malos = [i for i in got if (i.get("price") or "") and "2450" in i["price"]]
        check("14 · un nombre acabado en número no se pega al importe", not malos,
              f"precio fabricado: {[i.get('price') for i in got]} (el anuncio son 50 €)")

        browser.close()

    print()
    if fails:
        print(f"✗ {len(fails)} sin cumplir: {', '.join(fails)}")
        return 1
    print("✓ el extractor lee el precio entero y saca el nombre de la tarjeta sin inventarlo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
