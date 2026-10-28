"""V2-797 — a result card is laid out by the space it REALLY has, not by a character budget. RENDERED.

The operator: «se ve fatal ahora, y debe ser genérico: monta un sistema para que cualquier resultado se monte bien,
adecuado al UI, a las ventanas, al espacio y formato disponibles. Nada de parches.» The sheet used to budget
characters per field (title 34, subtitle 70): the server cut real listing names and reported «the payload breaks
the card» on every delivery, while a card without a photo fell to another shape and a dead photo left an empty
white box in a dark sheet.

What is measured here, painted in a real browser with the desktop's own design tokens (dark theme), at THREE card
sizes — narrow (a side column), medium, wide (maximised) — with long names, a missing photo and a dead one:

  1. nothing overflows sideways at any size;
  2. the grid reflows: one column narrow, more as the sheet widens;
  3. every title holds its two lines, and «Ver todo» shows it WHOLE (and the hover title carries it);
  4. every card of a photo layout has its plate — a monogram for a missing or dead photo — and plates of a row
     are the same height;
  5. the meta chips are one line each;
  6. the cards of a row are the same box, their footers aligned;
  7. a card is one rung above the sheet it sits on (`--hb-bg-soft` on `--hb-bg`).

Set RESULTS_SHOT=<path.png> to save a picture of the three sizes side by side.
"""
from __future__ import annotations

import asyncio
import base64
import os
import struct
import zlib

import pytest
from tests.browser import widget_client

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_PALETTE = os.path.join(ENG, "frontend", "app", "core", "palette.css")
SIZES = {"narrow": 340, "medium": 640, "wide": 1100}


def _png(w: int, h: int, rgb=(120, 140, 170)) -> str:
    def chunk(tag: bytes, body: bytes) -> bytes:
        c = tag + body
        return struct.pack(">I", len(body)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


LONG = ("RESTAURANTE CASA AUGUSTO ARRANZ | SORIA - Cocina castellana tradicional, asados en horno de leña y "
        "bodega con más de doscientas referencias")
SHEET = {
    "title": "Any errand", "tab": "results",
    "items": [
        {"title": LONG, "subtitle": "Ofrecemos una verdadera cocina castellana con productos de temporada " * 3,
         "price": "25–35 €", "score": {"value": 8.7, "max": 10}, "url": "https://example.invalid/a",
         "image": _png(640, 420), "meta": [{"label": "Distance", "value": "350 m"}, "13:00–16:00",
                                            {"label": "Phone", "value": "975 00 00 00"}],
         "facts": [{"label": "Distance", "value": "350 m"}]},
        {"title": "Madrid → Lisbon · direct flight, 1 h 20 min, morning departure with a checked bag",
         "subtitle": "Economy", "price": "89 €", "url": "https://example.invalid/b",
         "facts": [{"label": "Departs", "value": "07:45"}, {"label": "Bag", "value": "23 kg"}]},
        {"title": "Paella pan 46 cm, polished steel", "subtitle": "6 servings", "price": "24,90 €",
         "url": "https://example.invalid/c", "image": "https://dead.invalid/missing.jpg",
         "facts": [{"label": "Diameter", "value": "46 cm"}]},
        {"title": "A portrait product shot that is much taller than it is wide, with a long descriptive name",
         "price": "12 €", "url": "https://example.invalid/d", "image": _png(200, 600),
         "facts": [{"label": "Size", "value": "M"}]},
    ],
}

_MEASURE = """(id) => {
  const host = document.getElementById(id);
  const cards = [...host.querySelectorAll('.hr-card')];
  const cs = getComputedStyle(host);
  const rootStyle = getComputedStyle(document.documentElement);
  const rows = {};
  cards.forEach(c => { const r = c.getBoundingClientRect(); (rows[Math.round(r.top)] ||= []).push(c); });
  const firstRow = Object.values(rows)[0] || [];
  const lh = parseFloat(getComputedStyle(host.querySelector('.hr-card .hr-t')).lineHeight);
  return {
    // the GRID, not the host: the panel reaches into the host's gutter on purpose (V2-821, `.hr-panel` margins)
    hostW: host.querySelector('.hr-grid').clientWidth, scrollW: host.querySelector('.hr-grid').scrollWidth,
    overflow: cards.some(c => c.getBoundingClientRect().right > host.getBoundingClientRect().right + 1),
    cols: firstRow.length,
    lh,
    titleH: cards.map(c => c.querySelector('.hr-t').getBoundingClientRect().height),
    titleAttr: cards.map(c => c.querySelector('.hr-t').title),
    plates: cards.map(c => !!c.querySelector('.hr-shot')),
    monos: cards.map(c => !!c.querySelector('.hr-shot .hr-mono')),
    layout: host.querySelector('.hr-grid').dataset.layout,
    rowPlateH: Object.values(rows).map(r => r.map(c => {
      const p = c.querySelector('.hr-shot'); return p ? Math.round(p.getBoundingClientRect().height) : null; })),
    rowCardH: Object.values(rows).map(r => r.map(c => Math.round(c.getBoundingClientRect().height))),
    rowFoot: Object.values(rows).map(r => r.map(c => {
      const f = c.querySelector('.hr-foot'); return f ? Math.round(f.getBoundingClientRect().bottom) : null; })),
    chipOneLine: [...host.querySelectorAll('.hr-card .hr-chip')].every(ch => {
      const s = getComputedStyle(ch); return ch.getBoundingClientRect().height <= parseFloat(s.lineHeight) * 1 +
        parseFloat(s.paddingTop) + parseFloat(s.paddingBottom) + 2; }),
    chips: host.querySelectorAll('.hr-card .hr-chip').length,
    cardBg: getComputedStyle(cards[0]).backgroundColor,
    softBg: (() => { const p = document.createElement('div'); p.style.background = 'var(--hb-bg-soft)';
                     document.body.appendChild(p); const v = getComputedStyle(p).backgroundColor; p.remove(); return v; })(),
    sheetBg: cs.backgroundColor,
  };
}"""

_EXPAND = """async (id) => {
  const host = document.getElementById(id);
  const card = host.querySelector('.hr-card');
  const btn = card.querySelector('.hr-xbtn');
  const shown = btn && getComputedStyle(btn).display !== 'none';
  if (btn) btn.click();
  await new Promise(r => setTimeout(r, 80));
  const cl = card.querySelector('.hr-t .hr-cl');
  return {offered: shown, expanded: card.classList.contains('hr-x'),
          whole: cl.scrollHeight <= cl.clientHeight + 1, h: card.querySelector('.hr-t').getBoundingClientRect().height,
          text: cl.textContent};
}"""


def _paint():
    async def run():
        from playwright.async_api import async_playwright
        palette = open(_PALETTE, encoding="utf-8").read()
        hosts = "".join(f"<div class='win' style='width:{w}px'><div id='{k}'></div></div>" for k, w in SIZES.items())
        html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{palette}"
                "body{margin:0;padding:16px;background:var(--canvas);display:flex;gap:16px;align-items:flex-start}"
                ".win{background:var(--hb-bg);border-radius:12px;padding:16px;box-sizing:content-box}"
                ".hb-results{background:var(--hb-bg)}</style></head><body>" + hosts + "</body></html>")
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": sum(SIZES.values()) + 200, "height": 1400})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/", lambda route: asyncio.ensure_future(
                route.fulfill(status=200, content_type="text/html", body=html)))
            await pg.route("https://dead.invalid/**", lambda route: asyncio.ensure_future(route.abort()))
            await pg.goto("http://zaelar.test/")
            await widget_client.mount(pg, "results")
            for k in SIZES:
                await pg.evaluate("""([id, d]) => window.render(document.getElementById(id), d, {
                    action: async () => ({ok: true}), top: () => {}, scroll: () => {}})""", [k, SHEET])
            await pg.wait_for_timeout(500)
            out = {k: await pg.evaluate(_MEASURE, k) for k in SIZES}
            shot = os.environ.get("RESULTS_SHOT")
            if shot:
                await pg.screenshot(path=shot, full_page=True)
            out["expand"] = {k: await pg.evaluate(_EXPAND, k) for k in SIZES}
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(run())


@pytest.fixture(scope="module")
def m():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright is required for the rendered card contract")
    return _paint()


def test_it_paints_without_errors(m):
    assert m["errors"] == [], m["errors"]


@pytest.mark.parametrize("size", list(SIZES))
def test_nothing_overflows_sideways(m, size):
    r = m[size]
    assert r["scrollW"] <= r["hostW"] + 1 and not r["overflow"], r


def test_the_grid_reflows_with_the_width(m):
    assert m["narrow"]["cols"] == 1, m["narrow"]["cols"]
    assert m["wide"]["cols"] >= 3, m["wide"]["cols"]
    assert m["narrow"]["cols"] <= m["medium"]["cols"] <= m["wide"]["cols"]


@pytest.mark.parametrize("size", list(SIZES))
def test_a_long_title_holds_its_two_lines(m, size):
    r = m[size]
    assert max(r["titleH"]) <= r["lh"] * 2 + 2, (r["titleH"], r["lh"])


@pytest.mark.parametrize("size", list(SIZES))
def test_the_whole_title_is_one_click_away(m, size):
    x = m["expand"][size]
    assert x["offered"], "a clamped title offers no «Ver todo»"
    assert x["expanded"] and x["whole"] and x["text"] == LONG, x
    assert m[size]["titleAttr"][0] == LONG, "the hover title must carry the whole name"


@pytest.mark.parametrize("size", list(SIZES))
def test_every_card_keeps_its_plate_and_a_missing_photo_says_what_it_is(m, size):
    r = m[size]
    assert r["layout"] in ("split", "gallery"), r["layout"]
    assert all(r["plates"]), f"a card lost its plate: {r['plates']}"
    assert r["monos"][1] and r["monos"][2], f"no monogram for the missing / dead photo: {r['monos']}"
    for row in r["rowPlateH"]:
        assert max(row) - min(row) <= 1, f"plates of one row differ: {row}"


@pytest.mark.parametrize("size", list(SIZES))
def test_meta_chips_are_one_line_each(m, size):
    assert m[size]["chips"] >= 4 and m[size]["chipOneLine"], m[size]


def test_the_cards_of_a_row_are_the_same_box(m):
    r = m["wide"]
    for hs, fs in zip(r["rowCardH"], r["rowFoot"]):
        assert max(hs) - min(hs) <= 1, f"cards of one row differ in height: {hs}"
        assert max(fs) - min(fs) <= 1, f"footers do not line up: {fs}"


def test_a_card_is_one_rung_above_its_sheet(m):
    r = m["wide"]
    assert r["cardBg"] == r["softBg"] and r["cardBg"] != r["sheetBg"], r


# CRIT-K20 on the rendered grid (refactor2710-12; these two used to be read in the source, node 4.10): the payload's
# `columns` only CAPS the distribution, and the gap the grid subtracts is the gap it paints — a copied number made
# `auto-fill` drop a column on a 1 420 px sheet.
_GRID = """(id) => {
  const grid = document.getElementById(id).querySelector('.hr-grid');
  const cards = [...grid.querySelectorAll('.hr-card')].map(c => c.getBoundingClientRect());
  const top = cards.length ? Math.round(cards[0].top) : 0;
  const row = cards.filter(r => Math.round(r.top) === top);
  return {cols: row.length, gridW: grid.clientWidth, cardW: row.length ? row[0].width : 0,
          spacing: row.length > 1 ? row[1].left - row[0].right : null,
          gap: parseFloat(getComputedStyle(grid).columnGap)};
}"""
_CAPS = {"wide_free": (1420, None), "wide_cap2": (1420, 2), "narrow_cap4": (340, 4)}


def _grids():
    async def run():
        from playwright.async_api import async_playwright
        palette = open(_PALETTE, encoding="utf-8").read()
        hosts = "".join(f"<div style='width:{w}px'><div id='{k}'></div></div>" for k, (w, _) in _CAPS.items())
        html = f"<!doctype html><html><head><meta charset='utf-8'><style>{palette}</style></head><body>{hosts}</body></html>"
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 1600, "height": 1400})
            await pg.route("http://zaelar.test/", lambda route: asyncio.ensure_future(
                route.fulfill(status=200, content_type="text/html", body=html)))
            await pg.route("https://dead.invalid/**", lambda route: asyncio.ensure_future(route.abort()))
            await pg.goto("http://zaelar.test/")
            await widget_client.mount(pg, "results")
            sheet = {**SHEET, "items": SHEET["items"] * 2}
            for k, (_, cap) in _CAPS.items():
                await pg.evaluate("""([id, d]) => window.render(document.getElementById(id), d, {
                    action: async () => ({ok: true}), top: () => {}, scroll: () => {}})""",
                                  [k, {**sheet, **({"columns": cap} if cap else {})}])
            await pg.wait_for_timeout(300)
            out = {k: await pg.evaluate(_GRID, k) for k in _CAPS}
            await b.close()
            return out
    return asyncio.run(run())


@pytest.fixture(scope="module")
def grids(m):
    return _grids()


def test_the_payload_only_caps_the_columns_the_width_decides(grids):
    assert grids["wide_free"]["cols"] >= 3, grids["wide_free"]
    assert grids["wide_cap2"]["cols"] == 2, grids["wide_cap2"]
    assert grids["narrow_cap4"]["cols"] == 1, "a cap is a ceiling, never a number of columns to force"


def test_the_gap_the_grid_subtracts_is_the_gap_it_paints(grids):
    g = grids["wide_free"]
    assert g["spacing"] is not None and abs(g["spacing"] - g["gap"]) <= 1, g
    left = g["gridW"] - (g["cols"] * g["cardW"] + (g["cols"] - 1) * g["gap"])
    assert left < g["cardW"] + g["gap"], f"room for one more column was left empty: {g}"
