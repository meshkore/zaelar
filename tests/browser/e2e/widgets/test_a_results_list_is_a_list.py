"""V2-703 — a results LIST is a list, and the templates are the worker's to choose.

The operator, with two screenshots of the pot search V2-702 had just fixed:

> «Los resultados aparecen en una línea horizontal y cada cosa en su sitio. Son cajitas bien puestas,
> plantilladas y tenemos varias que le ofrecemos al Brainworker para que elija la más adecuada para cada lista
> de resultados. […] el botón de ver en Amazon es el que aparece en la ficha. […] asegúrate de que estos objetos
> plantillados soportan más o menos contenido y que todo va a quedar siempre bien y que se controla cada tamaño
> de campo. Fíjate además que en las listas de resultados puede haber menos datos para que quepan más
> resultados. Si un resultado solo ya ocupa toda la pantalla, ¿de qué me sirve la lista de resultados y tener
> acceso a la ficha? Lo que queremos es los datos principales, la foto y un botón para entrar en la ficha
> ampliada. Ni siquiera el botón de ver en Amazon en la propia lista de resultados.»

and, on who decides what goes in a card:

> «El worker se supone que tiene que tener la inteligencia suficiente como para decidir qué datos ponemos en
> esas fichas de resultados. Esto no es una página web, esto es un sistema dinámico e inteligente que tiene que
> soportar cualquier tipo de resultado, tanto si buscamos barcos como cafeteras, como recetas, como eventos
> históricos de la Primera Guerra Mundial.»

So the split this file pins down: the TEMPLATE owns the geometry and the budget of every slot; the WORKER owns
which template and which datum goes in each slot; and the LIST is a list — the record is where everything else
lives, including the way out to the shop.

RENDERED, for the same reason V2-702's file is: «one result fills the screen» and «the boxes are all the same
height» are questions about rectangles, and no source scan answers them.
"""
from __future__ import annotations

import asyncio
import base64
import os
import struct
import zlib

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "results", "widget.js")


def _png(w: int, h: int) -> str:
    """A real PNG of an exact size as a data: URI — the harness must not reach the network, and a 404 image
    removes itself, which would make «the photos line up» pass for the wrong reason."""
    def chunk(tag: bytes, body: bytes) -> bytes:
        c = tag + body
        return struct.pack(">I", len(body)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes((200, 205, 215)) * w for _ in range(h))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


_SHOT = _png(320, 251)

#: The seven `facts` his real item carried. They are in the fixture ON PURPOSE: the property under test is that
#: the LIST does not draw them, which cannot be measured with a sheet that never had any.
_FACTS = [{"label": "Capacidad", "value": "4 L (4,1 L según fabricante) — verificada vía marca + 2 retailers"},
          {"label": "Diámetro base", "value": "18 cm (formato alto 18 x 16 cm)"},
          {"label": "Tapa", "value": "Cristal con aro inox"},
          {"label": "Inducción", "value": "Sí — base encapsulada de 3 capas full induction"},
          {"label": "Material", "value": "Acero inoxidable 18/10"},
          {"label": "Marca", "value": "VIER"},
          {"label": "ASIN", "value": "B075WGKKGB"}]


def _item(title, price, *, primary=False, subtitle="Olla alta 18/10 · O18 x 16 cm · tapa cristal",
          badge="", image=_SHOT, score=9.2, url="https://www.amazon.es/dp/B075WGKKGB"):
    it = {"title": title, "subtitle": subtitle, "price": price, "facts": _FACTS}
    if primary:
        it["primary"] = True
    if badge:
        it["badge"] = badge
    if image:
        it["image"] = image
        it["images"] = [image]
    if score:
        it["score"] = {"value": score, "max": 10, "why": "el único que cumple los 5 criterios duros"}
    if url:
        it["url"] = url
    return it


def _sheet(items=None, **over):
    s = {"title": "Cacerola inox 18cm · tapa cristal · 4L+ · inducción", "tab": "results",
         "items": items if items is not None else [
             _item("VIER Olla Alta OI18", "EUR 17,36", primary=True, badge="ONLY 100% MATCH"),
             _item("IBILI Super Alta 24 cm", "EUR 24,90", score=8.1),
             _item("Fagor Alaia Olla Alta 20 cm con tapa de cristal templado y triple fondo encapsulado",
                   "EUR 31,45", score=7.6),
         ]}
    s.update(over)
    return s


_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202b;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
--hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-bubble:#1b2735;--hb-ok:#1f9d55;
--hb-warn-ink:#e0a355;--hb-danger:#d6455d;
--s1:4px;--s2:8px;--s3:12px;--s4:16px;--s5:24px;--r-sm:6px;--r-md:10px;--r-lg:14px;--line:1px solid #243244;
--f-micro:10px;--f-sm:12px;--f-body:13px;--f-md:15px;--f-lg:18px}
body{margin:0;background:#0a1017;padding:0}#host{width:1140px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.hb-results');
  if(!el) return {mounted:false};
  const cards = [...el.querySelectorAll('.hr-card')];
  const rect = e => { const r = e.getBoundingClientRect();
                      return {x:Math.round(r.left), y:Math.round(r.top),
                              w:Math.round(r.width), h:Math.round(r.height)}; };
  const rows = {};
  cards.forEach(c => { const r = rect(c); (rows[r.y] ||= []).push(r); });
  return {
    mounted: true,
    n: cards.length,
    grids: el.querySelectorAll('.hr-grid').length,
    grid_layout: (el.querySelector('.hr-grid') || {}).dataset ? el.querySelector('.hr-grid').dataset.layout : null,
    classes: cards.map(c => c.className),
    boxes: cards.map(rect),
    rows: Object.keys(rows).map(y => rows[y]),
    // what the LIST offers as a way forward
    detail_buttons: el.querySelectorAll('.hr-card .hr-more').length,
    out_links: el.querySelectorAll('.hr-card .hr-open').length,
    card_anchors: cards.filter(c => c.tagName === 'A').length,
    facts_in_list: el.querySelectorAll('.hr-card .hr-facts').length,
    badges: el.querySelectorAll('.hr-card .hr-badge').length,
    // ⚠️ COUNTING the badge in the DOM says nothing about whether it is on SCREEN: a row with a max-height
    // clips it and leaves the element exactly where it was. So: is the badge's box inside the box that clips
    // it? That is the operator's question, and it survives whatever CSS is used to hide it.
    badges_visible: [...el.querySelectorAll('.hr-card .hr-badge')].filter(b => {
      const r = b.getBoundingClientRect();
      if(!r.height || !r.width) return false;
      for(let a = b.parentElement; a && a.classList && !a.classList.contains('hr-grid'); a = a.parentElement){
        const cs = getComputedStyle(a);
        if(cs.overflow !== 'visible'){
          const ar = a.getBoundingClientRect();
          if(r.bottom > ar.bottom + 1 || r.top < ar.top - 1) return false;
        }
      }
      return true;
    }).length,
    // the line budget, measured on the box the browser actually laid out
    title_heights: [...el.querySelectorAll('.hr-card .hr-t')].map(t => Math.round(t.getBoundingClientRect().height)),
    line_h: (() => { const t = el.querySelector('.hr-card .hr-t');
                     return t ? Math.round(parseFloat(getComputedStyle(t).lineHeight) || 20) : 20; })(),
    foot_bottoms: [...el.querySelectorAll('.hr-card .hr-foot')]
      .map(f => Math.round(f.getBoundingClientRect().bottom)),
  };
}"""

_DETAIL = """() => {
  const el = document.querySelector('.hb-results');
  return {
    open: !!el.querySelector('.hr-back'),
    out_links: [...el.querySelectorAll('a[href]')].map(a => a.href),
    facts: el.querySelectorAll('.hr-facts').length,
  };
}"""


def _paint(sheet, *, width=1140, click_detail=False):
    async def run():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": width + 60, "height": 1200})
            errors, sent = [], []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/",
                           lambda route: asyncio.ensure_future(
                               route.fulfill(status=200, content_type="text/html", body=_HTML)))
            await pg.goto("http://zaelar.test/")
            await pg.evaluate("w => document.getElementById('host').style.width = w + 'px'", width)
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            await pg.expose_function("_send", lambda n, p: (sent.append((n, p)), {"ok": True})[1])
            await pg.evaluate("""d => window.render(document.getElementById('host'), d, {
                action: async (n, p) => await window._send(n, p), top: () => {}, scroll: () => {}})""", sheet)
            await pg.wait_for_timeout(350)
            out = await pg.evaluate(_MEASURE)
            if click_detail:
                btn = await pg.query_selector(".hr-card .hr-more")
                assert btn is not None, "there is no detail button to press"
                await btn.click()
                await pg.wait_for_timeout(250)
                out["detail"] = await pg.evaluate(_DETAIL)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(run())


@pytest.fixture(scope="module")
def wide():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return _paint(_sheet())


# ── THE LIST IS A LIST ──────────────────────────────────────────────────────────────────────────────────────

def test_it_mounts_without_a_single_error(wide):
    assert wide["mounted"], "the sheet did not paint"
    assert wide["errors"] == [], wide["errors"]


def test_the_results_sit_in_ONE_horizontal_row(wide):
    """«Los resultados aparecen en una línea horizontal y cada cosa en su sitio.»

    Three results, 1140px: they belong side by side. What he was looking at put the featured one alone on a
    full-width row and held the rest to two columns, so a three-result list read as two unrelated blocks.
    """
    assert wide["grids"] == 1, "one list, one grid — a second grid is a second, unrelated block"
    assert len(wide["rows"]) == 1, f"the results did not share a row: {wide['rows']}"
    assert wide["n"] == 3


def test_the_featured_result_is_MARKED_not_INFLATED(wide):
    """«Si un resultado solo ya ocupa toda la pantalla, ¿de qué me sirve la lista de resultados?»"""
    widths = {b["w"] for b in wide["boxes"]}
    assert max(widths) - min(widths) <= 2, f"the cards are not the same width: {sorted(widths)}"
    assert max(widths) < 600, f"a card in a three-result list is {max(widths)}px wide"
    assert any("primary" in c for c in wide["classes"]), "the featured one is still told apart, by its class"


def test_every_box_in_a_row_is_the_SAME_box(wide):
    """«Son cajitas bien puestas, plantilladas.» A template whose height depends on how talkative one result
    happens to be is not a template — and unequal cards put the buttons at three different heights."""
    hs = {b["h"] for b in wide["boxes"]}
    assert len(hs) == 1, f"the cards are of different heights: {sorted(hs)}"
    bottoms = set(wide["foot_bottoms"])
    assert len(bottoms) == 1, f"the «Ver detalle» buttons do not line up: {sorted(bottoms)}"


def test_a_LONG_title_spends_its_budget_and_stops(wide):
    """«Se controla cada tamaño de campo.» The third item's title is 89 characters; unbudgeted it rendered four
    lines and pushed everything under it down, which is how one result grows taller than its neighbours."""
    lh = wide["line_h"]
    tallest = max(wide["title_heights"])
    assert tallest <= lh * 2 + 4, f"a title is {tallest}px with a {lh}px line — the budget is not being applied"


def test_the_spec_sheet_does_NOT_come_to_the_list(wide):
    """«En las listas de resultados puede haber menos datos para que quepan más resultados.» Every item in the
    fixture carries seven `facts` precisely so that drawing none of them is the thing measured."""
    assert wide["facts_in_list"] == 0


def test_the_way_out_to_the_SHOP_belongs_to_the_record(wide):
    """«El botón de ver en Amazon es el que aparece en la ficha. […] Ni siquiera el botón de ver en Amazon en la
    propia lista de resultados.» One way forward per row: open the record."""
    assert wide["out_links"] == 0, "the list is offering a second button"
    assert wide["card_anchors"] == 0, "nor is the whole card quietly the outbound link"
    assert wide["detail_buttons"] == 3, "…and every result can still be opened"


def test_the_label_that_says_WHY_it_leads_survives(wide):
    """The budget clips the subtitle, never the badge: «ONLY 100% MATCH» is the one line that explains the
    order of the list, and it was the first thing a two-line subtitle pushed out of the card."""
    assert wide["badges"] == 1
    assert wide["badges_visible"] == 1, "the badge is in the DOM but clipped out of its card"


# ── …AND THE RECORD IS WHERE EVERYTHING ELSE LIVES ──────────────────────────────────────────────────────────

def test_the_record_carries_the_facts_AND_the_link(wide):
    """The other half of every assertion above: what leaves the list has to arrive somewhere. A list that drops
    the shop link and a record that never had one is not a tidier list, it is a dead end (V2-702's defect)."""
    out = _paint(_sheet(), click_detail=True)
    d = out["detail"]
    assert d["open"], "the record did not open"
    assert d["facts"] >= 1, "the spec sheet did not arrive at the record either"
    assert any("amazon.es" in h for h in d["out_links"]), f"no way out to the shop: {d['out_links']}"


def test_a_result_with_no_record_keeps_its_own_way_out():
    """The exception that is not one. When there is nothing to open, the card IS the link — otherwise removing
    the button from the list would strand results that have no record at all."""
    bare = [{"title": "Una nota suelta", "url": "https://example.com/x"}]
    out = _paint(_sheet(bare))
    assert out["detail_buttons"] == 0
    assert out["card_anchors"] == 1, "a result with nowhere to go and no link is a dead end"


# ── THE TEMPLATES ARE THE WORKER'S TO CHOOSE ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("asked,drawn", [("card", "split"), ("tile", "gallery"), ("row", "rows"),
                                         ("split", "split"), ("gallery", "gallery"), ("rows", "rows")])
def test_the_worker_names_the_template_and_gets_it(asked, drawn):
    """«Tenemos varias que le ofrecemos al Brainworker para que elija la más adecuada para cada lista.»

    The vocabulary is the worker's (card/tile/row), the classes are the drawing, and the internal names are
    accepted too so sheets written before this vocabulary existed keep rendering.
    """
    out = _paint(_sheet(layout=asked))
    assert all(drawn in c for c in out["classes"]), f"asked for {asked}, drew {out['classes']}"


def test_a_template_that_CANNOT_be_honoured_falls_back_instead_of_breaking():
    """A photo template over results with no photos draws a column of empty plates — and in `split`, whose two
    tracks are «plate» and «data», it drops the title into the plate's track. The guard is what lets the worker
    choose without being able to break the screen."""
    noshot = [_item("Batalla del Somme", "", image=None, subtitle="1 jul – 18 nov de 1916", score=None, url=""),
              _item("Batalla de Verdún", "", image=None, subtitle="21 feb – 18 dic de 1916", score=None, url="")]
    out = _paint(_sheet(noshot, layout="card"))
    assert all("rows" in c for c in out["classes"]), f"drew a photo template with no photos: {out['classes']}"
    # ⚠️ The line above passes whether or not the GUARD ran: `makeCard` degrades each card on its own when it
    # has no photo. What is under test here is the list-level DECISION — it also sizes the grid tracks — so it
    # is read from where the decision is written down.
    assert out["grid_layout"] == "rows", (
        f"the guard let an impossible template through; the grid is still sized for {out['grid_layout']}")


def test_a_template_NOBODY_offers_is_ignored_rather_than_obeyed():
    """An invented name must not reach the class list — that is how a worker's typo becomes a CSS selector
    nobody wrote. It falls through to the surface's own choice, which is the behaviour that existed before."""
    out = _paint(_sheet(layout="carrusel-3d"))
    assert all("carrusel" not in c for c in out["classes"]), out["classes"]
    assert out["grid_layout"] == "split", "it should land on what the content says it is"


def test_the_same_LIST_rules_hold_in_every_template():
    """The budget is the template's, but «a list is a list» is the surface's, and it cannot be opted out of by
    choosing a different one."""
    for asked in ("card", "tile", "row"):
        out = _paint(_sheet(layout=asked))
        assert out["facts_in_list"] == 0, f"{asked} drew the spec sheet"
        assert out["out_links"] == 0, f"{asked} drew the shop link"
        assert out["grids"] == 1, f"{asked} split the list into blocks"
