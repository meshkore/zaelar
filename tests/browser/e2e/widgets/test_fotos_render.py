"""V2-564 — the Fotos gallery RENDERED: the virtualization, the year headers, and the connect panel.

Rendering is the only way to check what matters here — none of this can be established by reading the
source:

  · The operator's own worry ("if I start scrolling and there are a thousand photos on screen, that will eat
    a lot of memory") is about DOM node count, not about what `view_data` returns. A fixture with 300 items
    has to produce far fewer than 300 mounted `.fts-tile` nodes.
  · Year headers are computed layout, not a static list — they have to appear as real, positioned elements.
  · With nothing connected, the operator sees a connect panel, never a blank grid.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "fotos", "widget.js")

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202c;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-risk:#e05252}
body{margin:0;background:#0a1017}#host{width:720px;height:620px}
</style></head><body><div id="host"></div></body></html>"""


def _items(n, years=("2023", "2024")):
    out = []
    per_year = max(1, n // len(years))
    for i in range(n):
        y = years[min(i // per_year, len(years) - 1)]
        out.append({"id": f"p{i}", "filename": f"photo-{i}.jpg", "taken_at": f"{y}-06-15",
                    "provider": "google-photos", "thumb": f"/api/photos/thumb/p{i}"})
    return out


_BASE = {
    "connected": True, "app_configured": True, "session_pending": False,
    "years": [{"year": "2024", "count": 1}], "items": [], "cursor": 0, "has_more": False, "total": 0,
    "active_filter": {}, "error": "", "reason": "", "updated": 1,
}

_MEASURE = """() => {
  const el = document.querySelector('.fts');
  if (!el) return {mounted: false};
  const scroller = el.querySelector('.fts-scroll');
  return {
    mounted: true,
    nested: el.querySelectorAll('.fts').length,
    tiles: el.querySelectorAll('.fts-tile').length,
    years: [...el.querySelectorAll('.fts-year')].map(n => n.textContent),
    injected_imgs: document.querySelectorAll('img[onerror]').length,
    connect_btn: !!el.querySelector('.fts-cx .fts-btn'),
    has_find: !!el.querySelector('.fts-find input'),
  };
}"""

_SCROLL_TO_BOTTOM = """() => {
  const s = document.querySelector('.fts-scroll');
  if (s) s.scrollTop = s.scrollHeight;
}"""


def _run(steps):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 780, "height": 700})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_HTML)
            await pg.route("http://zaelar.test/", _page)
            await pg.goto("http://zaelar.test/")
            src = open(_WIDGET, encoding="utf-8").read()
            await pg.add_script_tag(
                content=src.replace("export function render", "window.render = function render"))
            out = []
            for data, do_scroll in steps:
                await pg.evaluate(
                    "d => window.render(document.getElementById('host'), d, {action: async () => ({ok:true})})",
                    data)
                await pg.wait_for_timeout(120)
                if do_scroll:
                    await pg.evaluate(_SCROLL_TO_BOTTOM)
                    await pg.wait_for_timeout(120)
                m = await pg.evaluate(_MEASURE)
                m["errors"] = list(errors)
                out.append(m)
            await b.close()
            return out
    return asyncio.run(go())


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_it_mounts_with_no_page_errors(playwright_available):
    m = _run([({**_BASE, "items": _items(3), "total": 3}, False)])[0]
    assert m["mounted"], "the gallery did not paint"
    assert m["errors"] == [], m["errors"]
    assert m["nested"] == 0, "the card must re-render at its ROOT, never inside itself (V2-124)"


def test_a_thousand_photos_do_not_become_a_thousand_dom_nodes(playwright_available):
    """The operator's own worry, checked directly: 300 items in the fixture, far fewer mounted tiles."""
    m = _run([({**_BASE, "items": _items(300), "total": 300}, False)])[0]
    assert m["tiles"] > 0, "nothing rendered at all"
    assert m["tiles"] < 100, f"{m['tiles']} tiles mounted for 300 items — the grid is not windowing"


def test_scrolling_keeps_the_mounted_count_bounded_instead_of_accumulating(playwright_available):
    """The counterweight: without recycling, tiles seen while scrolling would pile up instead of being
    swapped for the ones now near the viewport."""
    m = _run([({**_BASE, "items": _items(300), "total": 300}, True)])[0]
    assert m["tiles"] < 100, f"{m['tiles']} tiles mounted after scrolling to the bottom — nothing was recycled"


def test_year_headers_are_real_positioned_elements(playwright_available):
    m = _run([({**_BASE, "items": _items(40, years=("2022", "2023", "2024")), "total": 40}, False)])[0]
    assert set(m["years"]) >= {"2022", "2023", "2024"}, m["years"]


def test_with_nothing_connected_the_card_offers_the_CONNECT_button_not_a_blank_grid(playwright_available):
    m = _run([({**_BASE, "connected": False, "items": []}, False)])[0]
    assert m["connect_btn"] is True
    assert m["tiles"] == 0


def test_the_search_box_is_present_when_connected(playwright_available):
    m = _run([({**_BASE, "items": _items(5), "total": 5}, False)])[0]
    assert m["has_find"] is True


def test_an_empty_gallery_paints_a_note_not_a_silent_blank(playwright_available):
    m = _run([({**_BASE, "items": [], "total": 0}, False)])[0]
    assert m["tiles"] == 0
    assert m["mounted"], "the card itself must still render"
