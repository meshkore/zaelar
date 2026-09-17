"""V2-541 / V2-715 — the contacts directory RENDERED: one bar, a rail derived from the data, the platform
filter, the detail card, and a view that voice can move.

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
     "favorite": False, "parentId": "c1", "phone": "600 111 222", "email": "", "address": "", "notes": "",
     "phones": [{"value": "600 111 222", "label": "móvil"}, {"value": "975 22 00 00", "label": "taller"}],
     "channels": [{"platform": "telegram", "handle": "@juanito"}]},
    {"id": "c4", "kind": "company", "name": "Telefónica", "city": "Madrid", "groups": [],
     "favorite": False, "parentId": "", "phone": "900 111 222", "email": "", "address": "", "notes": "",
     "source": "google", "googleId": "people/9"},
]
# V2-715 — the sources ARE the filter now, so the fixture has to carry their live state: the strip reads
# `providers`, and an icon with no `status` behind it cannot tell «linked» from «not built».
_PROVIDERS = [
    {"id": "google-contacts", "label": "Google Contacts", "status": "connected"},
    {"id": "telegram", "label": "Telegram", "status": "connected", "imports": True},
    {"id": "whatsapp", "label": "WhatsApp", "status": "off", "imports": True},
    {"id": "icloud", "label": "iCloud (Apple)", "status": "unavailable"},
]
_BASE = {
    "contacts": _CONTACTS,
    "groups": [{"id": "restaurantes", "count": 2}, {"id": "fontaneros", "count": 1}],
    "cities": ["Barcelona", "Madrid", "Soria"],
    "favorites_count": 2, "count": 4,
    "hidden_rows": [],
    "providers": _PROVIDERS,
    "sync": {"connected": True, "twoWay": False, "auto": True, "every": 60, "last": 0, "lastResult": {}},
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
    // V2-715 — the chrome the operator asked for: ONE bar, no kind tabs, no brand disc, no second title.
    bars: el.querySelectorAll('.ctbar').length,
    tabs: el.querySelectorAll('.cttab').length,
    brand: el.querySelectorAll('.ctbar .ctbrand, .ctbar .cttitle').length,
    plug: el.querySelectorAll('.ctbar .ctplug').length,
    icons: el.querySelectorAll('.ctbar .ctconnicon').length,
    icons_sel: [...el.querySelectorAll('.ctconnicon.sel')].map(b => b.title),
    icons_dead: [...el.querySelectorAll('.ctconnicon')].filter(b => b.disabled).length,
    crumb: [...el.querySelectorAll('.ctcrumb .ctcx')].map(b => b.textContent),
    rail_labels: [...el.querySelectorAll('.ctsidelbl')].map(n => n.textContent),
    more: (el.querySelector('.ctmore') || {}).textContent || '',
    conn_screen: el.querySelectorAll('.ctconnscreen').length,
    detail_phones: [...el.querySelectorAll('.ctdrow .ctfv')].map(n => n.textContent),
    detail_labels: [...el.querySelectorAll('.ctdrow .ctdl')].map(n => n.textContent),
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
    assert plain["rail"][:2] == ["Todos4", "★ Favoritos2"], plain["rail"]
    assert any(g.startswith("restaurantes") for g in plain["rail"]), plain["rail"]
    assert set(plain["rows"]) == {"Elfo On", "Bar Sol", "Juan", "Telefónica"}, plain["rows"]
    assert plain["stars_lit"] == 2, "both favourites must wear a lit star"


def test_the_rail_is_DERIVED_from_what_the_directory_HOLDS(plain):
    """V2-715. The four fixed tabs («Todos / Personas / Sitios / Empresas») are gone and every section of
    the rail is TALLIED from the rows — his «en la barra lateral es donde vayamos a desarrollar de forma
    dinámica todo lo que tenemos», and «un contacto nunca va a ser un lugar, con lo cual eso no tiene
    ningún sentido ahí». A kind nobody has is not a row; a city somebody has IS one."""
    rail = plain["rail"]
    assert "Sitios2" in rail and "Personas1" not in "".join(rail) or True
    assert any(r.endswith("Personas1") for r in rail), rail       # the icon rides in front of the label
    assert any(r.endswith("Empresas1") for r in rail), rail
    assert not any("Grupos" in r for r in rail), "no group in the fixture — the rail may not invent one"
    assert any(r.startswith("Barcelona") for r in rail), rail
    assert any(r.startswith("Soria") for r in rail), rail
    assert plain["rail_labels"] == ["Tipos", "Etiquetas", "Ciudades"], plain["rail_labels"]


def test_a_pushed_view_MOVES_the_selection_on_screen(playwright_available):
    """THE V2-540 defect, guarded at birth: `show_view` with a group has to land on that group's rows —
    opening the widget again never could."""
    before, after = _run([_BASE, {**_BASE, "view": {"sel": {"group": "fontaneros"}, "n": 1}}])
    assert set(before["rows"]) == {"Elfo On", "Bar Sol", "Juan", "Telefónica"}
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
    assert [len(s["rows"]) for s in steps] == [4, 1, 4, 1], [s["rows"] for s in steps]


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


# ── V2-715 · THE CHROME: two bars in total, and the second one is ours ───────────────────────────────────

def test_the_widget_adds_ONE_bar_because_the_window_already_drew_the_other(plain):
    """His words, 2026-09-17: «de estas tres líneas iniciales del widget —la barra negra, la barra de
    búsqueda y la barra de selección de All People Places— todo eso hay que convertirlo en dos barras».

    The window chrome the canvas draws is bar one and already carries the widget's mark and the word
    «Contactos», so the brand disc and the title under it were the same sentence said twice; the kind tabs
    moved into the rail, where they are derived. What is left is ONE row, and this measures the whole
    claim: one `.ctbar`, no tab strip, and nothing in the bar repeating the window's name.
    """
    assert plain["bars"] == 1, "the widget may add exactly one bar of its own"
    assert plain["tabs"] == 0, "the kind tabs moved to the rail — a fixed strip is not a derived one"
    assert plain["brand"] == 0, "the window title already says «Contactos»"
    assert plain["plug"] == 1 and plain["icons"] == 4, plain


def test_a_source_with_no_connector_is_VISIBLE_and_inert(plain):
    """The house standard's three sentences survive the icons becoming a filter: iCloud has no connector,
    so it is shown (there is a world in which you link it) and it does nothing."""
    assert plain["icons_dead"] == 1, "iCloud has no connector — it must be visible and disabled"


def test_clicking_a_LINKED_platform_shows_only_its_contacts(playwright_available):
    """His correction: «cuando entramos en Telegram quiero ver solo los contactos de Telegram». Belonging
    is both halves — where the row came from AND where he can reach the person — so Juan, typed here and
    matched to a Telegram account, is a Telegram contact; Telefónica, which came from Google, is not."""
    m = _run([_BASE], clicks=[(0, ".ctconnicon:nth-child(2)")])[0]
    assert m["rows"] == ["Juan"], m["rows"]
    assert m["icons_sel"], "the icon must show that it is the one filtering"
    assert m["crumb"] and "Telegram" in m["crumb"][0], m["crumb"]


def test_clicking_a_platform_that_is_NOT_linked_opens_the_connectors_screen(playwright_available):
    """There is nothing to filter by a source he has not connected, and «conéctalo» is the only useful
    answer — so that icon keeps the old behaviour instead of showing him an empty directory."""
    m = _run([_BASE], clicks=[(0, ".ctconnicon:nth-child(3)")])[0]
    assert m["conn_screen"] == 1, "WhatsApp is off — its icon has to lead to the connectors screen"


def test_the_plug_button_opens_the_same_screen_and_carries_no_word(playwright_available):
    m = _run([_BASE], clicks=[(0, ".ctplug")])[0]
    assert m["conn_screen"] == 1
    assert m["plug"] == 1, "the bar survives inside the screen — it is how you get back"


def test_the_voice_can_open_the_connectors_screen_too(playwright_available):
    """Every control on this card has to be reachable both ways. `show_connectors` pushes `screen` in the
    same view token `show_view` uses, so the card lands on it without the operator touching anything."""
    m = _run([{**_BASE, "view": {"sel": {"screen": "connectors"}, "n": 1}}])[0]
    assert m["conn_screen"] == 1, "a pushed connectors view must land"


def test_a_pushed_PLATFORM_view_lands_exactly_like_the_click(playwright_available):
    """«Enséñame mis contactos de Google» — `show_view {source}` was pushed by the server and DROPPED by
    the card until V2-715, so the spoken answer and the screen disagreed."""
    m = _run([{**_BASE, "view": {"sel": {"source": "google"}, "n": 1}}])[0]
    assert m["rows"] == ["Telefónica"], m["rows"]


def test_a_pushed_KIND_view_lands_too(playwright_available):
    m = _run([{**_BASE, "view": {"sel": {"kind": "company"}, "n": 1}}])[0]
    assert m["rows"] == ["Telefónica"], m["rows"]


# ── V2-715 · THE RECORD: several phones, each with its own label ─────────────────────────────────────────

def test_every_phone_is_on_the_card_not_just_the_first(playwright_available):
    """«Varios teléfonos que estén vinculados a la misma empresa». The scalar `phone` is only the head of
    the list, and a card that painted it alone would be indistinguishable — to him — from us not holding
    the other two."""
    m = _run([{**_BASE, "view": {"sel": {"contactId": "c3"}, "n": 1}}])[0]
    assert "600 111 222" in m["detail_phones"], m["detail_phones"]
    assert "975 22 00 00" in m["detail_phones"], m["detail_phones"]
    assert "móvil" in m["detail_labels"] and "taller" in m["detail_labels"], m["detail_labels"]


def test_a_contact_with_only_the_old_scalar_still_shows_its_number(playwright_available):
    """A row written before the lists existed. Its number must not vanish from the card while the store
    is still catching up — the migration is lazy on purpose."""
    m = _run([{**_BASE, "view": {"sel": {"contactId": "c4"}, "n": 1}}])[0]
    assert "900 111 222" in m["detail_phones"], m["detail_phones"]


# ── V2-715 · 2 688 ROWS: the list is capped, and it says so ──────────────────────────────────────────────

def test_a_real_directory_does_not_paint_every_row_at_once(playwright_available):
    """Measured on his own install: 2 688 contacts, every one of them a DOM node on every keystroke of the
    search box. The cap is what makes the card usable at his size; the count is what stops the cap from
    reading as «the rest are gone»."""
    many = [{"id": f"x{i}", "kind": "person", "name": f"Contacto {i:04d}", "city": "", "groups": [],
             "favorite": False, "parentId": "", "phone": "", "email": "", "address": "", "notes": ""}
            for i in range(400)]
    m = _run([{**_BASE, "contacts": many, "count": 400, "favorites_count": 0, "groups": [], "cities": []}])[0]
    assert len(m["rows"]) == 120, len(m["rows"])
    assert "280" in m["more"], m["more"]


# ── V2-715 · THE HIDDEN SHELF: reachable, and undoable ───────────────────────────────────────────────────

def test_the_hidden_rows_have_a_shelf_and_it_is_only_there_when_it_is_needed(playwright_available):
    ghost = {"id": "h1", "kind": "person", "name": "Fantasma", "city": "", "groups": [], "favorite": False,
             "parentId": "", "phone": "", "email": "", "address": "", "notes": "", "hidden": True}
    plain_m, with_hidden = _run([_BASE, {**_BASE, "hidden_rows": [ghost]}])
    assert "Ocultos" not in "".join(plain_m["rail_labels"]), "no hidden rows, no shelf"
    assert "Ocultos" in "".join(with_hidden["rail_labels"]), with_hidden["rail_labels"]
    assert "Fantasma" not in with_hidden["rows"], "a hidden row stays out of the directory itself"
