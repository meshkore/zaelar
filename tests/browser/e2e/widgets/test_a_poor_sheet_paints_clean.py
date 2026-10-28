"""V2-831 T-01 (node 4.324) — a results sheet with poor data still paints clean: photo layouts only when MOST rows have a photo,
and the item templates `offer` · `video` · `link`. RENDERED, because both are questions about rectangles.

2026-10-28, the operator's screenshot: one wide logo among thirteen rows flipped the whole list to photo plates and
twelve of them painted a monogram — «1» for the rows titled with a price. The recorded sheet is replayed through the
real door (`present` → `view_data`) and painted with the desktop's tokens at two widths.

Set RESULTS_SHOT=<path.png> to save a picture of each sheet.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
import zlib
from pathlib import Path

import pytest
from tests.browser import widget_client

ENG = Path(__file__).resolve().parents[4]
_PALETTE = ENG / "frontend" / "app" / "core" / "palette.css"
_EVIDENCE = ENG / "tests" / "browser" / "unit" / "results" / "fixtures" / "sheet_with_poor_rows_2026_10_28.json"
WIDTHS = {"narrow": 340, "wide": 900}


def _png(w: int, h: int, rgb=(120, 140, 170)) -> str:
    def chunk(tag: bytes, body: bytes) -> bytes:
        c = tag + body
        return struct.pack(">I", len(body)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _through_the_door(payload: dict, sheet_id: str) -> dict:
    """The sheet as the card receives it: the real `present` and `view_data`, on the suite's isolated store."""
    from widgets.results import data as sheet
    sheet.apply_action("present", {**payload, "sheet": sheet_id})
    return json.loads(json.dumps(sheet.view_data(sheet_id), default=str))


def _evidence() -> dict:
    ev = json.loads(_EVIDENCE.read_text(encoding="utf-8"))
    # the offer's wide logo, as a local image of the same shape (the harness never reaches the network)
    items = [{**it, "image": _png(320, 90)} if it.get("image") else it for it in ev["items"]]
    return {"title": ev["title"], "items": items}


SHEETS = {
    "evidence": lambda: _evidence(),
    "most_photos": lambda: {"title": "x", "items": [
        {"title": f"Pot {i}", "price": f"{10 + i} €", "url": "https://shop.invalid/p", "image": _png(400, 300)}
        for i in range(4)] + [{"title": "Pot without photo", "price": "9 €", "url": "https://shop.invalid/q"}]},
    "videos": lambda: {"title": "x", "kind": "video", "items": [
        {"title": f"How to fold a sail, part {i}", "subtitle": "Sailing channel · 12:40",
         "url": "https://video.invalid/w", "image": _png(480, 270)} for i in range(3)]},
}

_MEASURE = """(id) => {
  const host = document.getElementById(id);
  const cards = [...host.querySelectorAll('.hr-card')];
  const box = (el) => el ? el.getBoundingClientRect() : null;
  return {
    layout: (host.querySelector('.hr-grid') || {dataset: {}}).dataset.layout,
    // the GRID and its cards, not the host: the panel reaches into the host's gutter on purpose (V2-821)
    gridW: host.querySelector('.hr-grid').clientWidth, gridScrollW: host.querySelector('.hr-grid').scrollWidth,
    overflow: cards.some(c => box(c).right > box(host).right + 1
                              || [...c.querySelectorAll('*')].some(e => box(e).right > box(c).right + 1)),
    cards: cards.map(c => {
      const shot = c.querySelector('.hr-shot'), body = c.querySelector('.hr-body');
      const logo = c.querySelector('.hr-logo'), big = c.querySelector('.hr-bigprice');
      return {cls: c.className, title: c.querySelector('.hr-t').textContent,
              text: c.textContent, plate: !!shot, mono: !!c.querySelector('.hr-shot .hr-mono'),
              shot: shot ? [box(shot).left, box(shot).right, box(shot).width, box(shot).height] : null,
              body: body ? [box(body).left, box(body).top] : null,
              logo: logo ? [logo.getBoundingClientRect().width, logo.getBoundingClientRect().height] : null,
              big: big ? big.textContent : null, chips: c.querySelectorAll('.hr-chip').length,
              host: (c.querySelector('.hr-host') || {}).textContent || null,
              fav: !!c.querySelector('.hr-fav svg')};
    }),
  };
}"""


def _paint():
    sheets = {k: _through_the_door(f(), f"t01-{k}") for k, f in SHEETS.items()}

    async def run():
        from playwright.async_api import async_playwright
        hosts = "".join(f"<div class='win' style='width:{w}px'><div id='{k}-{n}'></div></div>"
                        for k in sheets for n, w in WIDTHS.items())
        html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{_PALETTE.read_text(encoding='utf-8')}"
                "body{margin:0;padding:16px;background:var(--canvas);display:flex;flex-wrap:wrap;gap:16px;"
                "align-items:flex-start}.win{background:var(--hb-bg);border-radius:12px;padding:16px}"
                ".hb-results{background:var(--hb-bg)}</style></head><body>" + hosts + "</body></html>")
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 1400, "height": 1600})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/", lambda route: asyncio.ensure_future(
                route.fulfill(status=200, content_type="text/html", body=html)))
            await pg.route("https://**", lambda route: asyncio.ensure_future(route.abort()))
            await pg.goto("http://zaelar.test/")
            await widget_client.mount(pg, "results")
            for k, d in sheets.items():
                for n in WIDTHS:
                    await pg.evaluate("""([id, d]) => window.render(document.getElementById(id), d, {
                        action: async () => ({ok: true}), top: () => {}, scroll: () => {}})""", [f"{k}-{n}", d])
            await pg.wait_for_timeout(500)
            out = {f"{k}-{n}": await pg.evaluate(_MEASURE, f"{k}-{n}") for k in sheets for n in WIDTHS}
            if os.environ.get("RESULTS_SHOT"):
                await pg.wait_for_timeout(1500)
                await pg.screenshot(path=os.environ["RESULTS_SHOT"], full_page=True)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(run())


@pytest.fixture(scope="module")
def m():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright is required for the rendered sheet")
    return _paint()


def test_it_paints_without_errors(m):
    assert m["errors"] == [], m["errors"]


@pytest.mark.parametrize("key", [f"{k}-{n}" for k in SHEETS for n in WIDTHS])
def test_nothing_overflows_sideways(m, key):
    r = m[key]
    assert r["gridScrollW"] <= r["gridW"] + 1 and not r["overflow"], key


@pytest.mark.parametrize("width", list(WIDTHS))
def test_one_logo_among_many_rows_never_makes_a_wall_of_monograms(m, width):
    r = m[f"evidence-{width}"]
    assert r["layout"] == "rows", r["layout"]
    assert not any(c["mono"] for c in r["cards"]), [c["title"] for c in r["cards"] if c["mono"]]
    assert len(r["cards"]) == 7 and not any(c["title"][:1].isdigit() for c in r["cards"])
    assert not any("<br" in c["text"] for c in r["cards"])


def test_most_rows_with_a_photo_still_get_the_photo_layout(m):
    r = m["most_photos-wide"]
    assert r["layout"] in ("split", "gallery") and all(c["plate"] for c in r["cards"]), r["layout"]


@pytest.mark.parametrize("width", list(WIDTHS))
def test_an_offer_leads_with_its_price_and_its_logo_never_takes_a_plate(m, width):
    offer = next(c for c in m[f"evidence-{width}"]["cards"] if c["title"] == "SkyShowtime")
    assert "k-offer" in offer["cls"] and not offer["plate"], offer
    assert offer["big"] == "6,99€" and offer["chips"] <= 2, offer
    assert offer["logo"] and offer["logo"][1] <= 24 and offer["logo"][0] > offer["logo"][1] * 2, offer["logo"]


@pytest.mark.parametrize("width", list(WIDTHS))
def test_a_bare_page_is_a_link_card_with_its_site(m, width):
    links = [c for c in m[f"evidence-{width}"]["cards"] if c["title"] != "SkyShowtime"]
    assert links and all("k-link" in c["cls"] and not c["plate"] for c in links), [c["cls"] for c in links]
    assert links[0]["host"] == "educa.jcyl.es" and links[0]["fav"], links[0]


def test_a_video_is_a_16_9_thumbnail_left_of_its_text(m):
    for c in m["videos-wide"]["cards"]:
        assert "k-video" in c["cls"] and c["shot"], c
        left, right, w, h = c["shot"]
        assert abs(w / h - 16 / 9) < 0.05, (w, h)
        assert right <= c["body"][0] + 1, "the text is not to the right of the thumbnail"
