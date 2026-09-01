"""V2-541 — the contacts directory RENDERED: rail, filters, detail, and a view that voice can move.

Rendering is the only way to check the half that matters: whether the group rail actually paints, whether a
pushed view MOVES what is on screen (and declines to move on a plain refresh), and whether opening a detail
re-renders at the ROOT instead of nesting the widget inside its own column (the detached-canvas family,
V2-124) — reading widget.js would only prove the code was written.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "contactos", "widget.js")

_CONTACTS = [
    {"id": "c1", "kind": "place", "name": "Elfo On", "city": "Soria", "groups": ["restaurantes"],
     "favorite": True, "parentId": "", "phone": "", "email": "", "address": "", "notes": ""},
    {"id": "c2", "kind": "place", "name": "Bar Sol", "city": "Barcelona", "groups": ["restaurantes"],
     "favorite": True, "parentId": "", "phone": "", "email": "", "address": "", "notes": ""},
    {"id": "c3", "kind": "person", "name": "Juan", "city": "Soria", "groups": ["fontaneros"],
     "favorite": False, "parentId": "c1", "phone": "600 111 222", "email": "", "address": "", "notes": ""},
]
_BASE = {
    "contacts": _CONTACTS,
    "groups": [{"id": "restaurantes", "count": 2}, {"id": "fontaneros", "count": 1}],
    "cities": ["Barcelona", "Soria"],
    "favorites_count": 2, "count": 3,
    "view": None,
}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-neutral:#c2ccda}
body{margin:0;background:#0a1017}#host{width:700px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.hb-contactos');
  if (!el) return {mounted: false};
  const rail = [...el.querySelectorAll('.ctg')].map(b => b.textContent);
  const on = [...el.querySelectorAll('.ctg')].find(b => b.classList.contains('on'));
  return {
    mounted: true,
    nested: el.querySelectorAll('.hb-contactos').length,
    rail,
    rail_on: on ? on.textContent : null,
    rows: [...el.querySelectorAll('.ctrow .ctnm')].map(n => n.textContent),
    chips: [...el.querySelectorAll('.ctfil .ctchip')].map(c => c.textContent),
    detail: (el.querySelector('.ctdet .ctdnm') || {}).textContent || '',
    detail_links: [...el.querySelectorAll('.ctdet .ctlink')].map(a => a.textContent),
    empty: (el.querySelector('.ctempty') || {}).textContent || '',
    stars_lit: el.querySelectorAll('.ctfav.on').length,
  };
}"""


def _run(steps, clicks=None):
    """Paint once, then apply each `data` through the SAME element — the way a live refresh does. `clicks`
    is an optional list of (after_step_index, selector) pairs applied before measuring the next state."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 740, "height": 900})
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
            for i, data in enumerate(steps):
                await pg.evaluate(
                    "d => window.render(document.getElementById('host'), d, {action: async () => ({})})", data)
                await pg.wait_for_timeout(50)
                for at, sel in (clicks or []):
                    if at == i:
                        await pg.click(sel)
                        await pg.wait_for_timeout(50)
                m = await pg.evaluate(_MEASURE)
                m["errors"] = errors
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


@pytest.fixture(scope="module")
def plain(playwright_available):
    return _run([_BASE])[0]


def test_it_mounts_with_the_rail_the_rows_and_no_errors(plain):
    assert plain["mounted"], "the directory did not paint"
    assert plain["errors"] == [], plain["errors"]
    assert plain["rail"][:2] == ["Todos3", "★ Favoritos2"], plain["rail"]
    assert any(g.startswith("restaurantes") for g in plain["rail"]), plain["rail"]
    assert set(plain["rows"]) == {"Elfo On", "Bar Sol", "Juan"}, plain["rows"]
    assert plain["stars_lit"] == 2, "both favourites must wear a lit star"


def test_the_filter_chips_are_DERIVED_from_the_data(plain):
    assert "★ favoritos" in plain["chips"], plain["chips"]
    assert "Barcelona" in plain["chips"] and "Soria" in plain["chips"], plain["chips"]


def test_a_pushed_view_MOVES_the_selection_on_screen(playwright_available):
    """THE V2-540 defect, guarded at birth: `show_view` with a group has to land on that group's rows —
    opening the widget again never could."""
    before, after = _run([_BASE, {**_BASE, "view": {"sel": {"group": "fontaneros"}, "n": 1}}])
    assert set(before["rows"]) == {"Elfo On", "Bar Sol", "Juan"}
    assert after["rows"] == ["Juan"], after["rows"]


def test_a_plain_refresh_does_NOT_yank_the_filter_the_operator_is_reading(playwright_available):
    steps = _run([_BASE,
                  {**_BASE, "view": {"sel": {"group": "fontaneros"}, "n": 1}},
                  {**_BASE, "view": {"sel": {"group": "fontaneros"}, "n": 1}}])
    assert steps[1]["rows"] == ["Juan"]
    assert steps[2]["rows"] == ["Juan"], "the refresh must not re-apply, but must not undo it either"


def test_asking_for_the_SAME_filter_twice_still_lands(playwright_available):
    """The token is a counter and not the filter: fontaneros → he clicks Todos himself → «fontaneros» again."""
    steps = _run([_BASE,
                  {**_BASE, "view": {"sel": {"group": "fontaneros"}, "n": 1}},
                  {**_BASE, "view": {"sel": {}, "n": 2}},
                  {**_BASE, "view": {"sel": {"group": "fontaneros"}, "n": 3}}])
    assert [len(s["rows"]) for s in steps] == [3, 1, 3, 1], [s["rows"] for s in steps]


def test_the_favourite_in_barcelona_view_shows_exactly_the_answer(playwright_available):
    m = _run([{**_BASE, "view": {"sel": {"group": "restaurantes", "city": "Barcelona",
                                          "favorites": True}, "n": 1}}])[0]
    assert m["rows"] == ["Bar Sol"], m["rows"]


def test_a_pushed_contact_opens_its_DETAIL_with_its_linked_people(playwright_available):
    m = _run([{**_BASE, "view": {"sel": {"contactId": "c1"}, "n": 1}}])[0]
    assert "Elfo On" in m["detail"], m["detail"]
    assert "Juan" in m["detail_links"], "the people connected to the place must be reachable from its card"


def test_opening_a_detail_by_CLICK_renders_at_the_root_not_nested(playwright_available):
    """The V2-124 family: a re-render targeted at the column would mount a second widget inside the first,
    silently. One `.hb-contactos` in the document, before and after."""
    m = _run([_BASE], clicks=[(0, ".ctrow")])[0]
    assert m["detail"], "clicking a row must open its card"
    assert m["nested"] == 0, "the widget re-rendered inside itself"
    assert m["errors"] == [], m["errors"]


def test_an_empty_directory_explains_how_to_fill_it(playwright_available):
    m = _run([{**_BASE, "contacts": [], "groups": [], "cities": [], "count": 0, "favorites_count": 0}])[0]
    assert "vacío" in m["empty"], m["empty"]
    assert "Zaelar" in m["empty"], "the empty state must teach the voice gesture, not just apologise"
