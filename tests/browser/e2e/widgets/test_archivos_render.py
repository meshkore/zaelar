"""V2-557 — the cloud file explorer RENDERED: rows, breadcrumb, the reason banner, and the XSS surface.

Rendering is the only way to check the half that matters here. Three of these cannot be established by reading
the source at all:

  · A file name is UNTRUSTED text from somebody's cloud drive. `<img src=x onerror=…>` is a legal file name in
    every provider we speak to. Only a browser can say whether that became an element or stayed a string.
  · The «this permission cannot list folders» banner is the whole point of answering ok+reason instead of an
    empty array (V2-557). A banner that exists in the DOM with zero height explains nothing to anybody.
  · The connect panel is what an operator with nothing connected actually sees. A card whose only state is a
    blank list is the failure this widget was written to avoid.

It also guards the shape V2-124 made expensive: re-rendering at the ROOT rather than nesting the widget inside
its own subtree, which fails with no error at all.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "archivos", "widget.js")

_ENTRIES = [
    {"id": "d1", "name": "Contratos", "kind": "folder", "mime": "", "size": None,
     "modified": "", "web_url": "", "provider": "gdrive"},
    {"id": "f1", "name": "Contrato Axa.pdf", "kind": "file", "mime": "application/pdf",
     "size": 1536, "modified": "2026-01-02T10:00:00Z", "web_url": "https://example.invalid/f",
     "provider": "gdrive"},
]
_PROVIDERS = [{"id": "gdrive", "label": "Google Drive", "connected": True, "app_configured": True,
               "tier": "browse", "tier_label": "Ver todo mi Drive", "browsable": True, "note": "",
               "default_tier": "browse",
               "tiers": [{"id": "browse", "label": "Ver todo mi Drive", "browsable": True, "note": "todo"},
                         {"id": "picked", "label": "Solo los que elija", "browsable": False, "note": "estrecho"}]}]

_BASE = {
    "provider": "gdrive", "providers": _PROVIDERS, "connected": True,
    "folder_id": "d1", "trail": [{"id": "d1", "name": "Contratos"}],
    "entries": _ENTRIES, "next": "", "query": "", "selected": None, "mode": "list",
    "panel": "", "error": "", "reason": "", "count": 2, "needs_refresh": False, "updated": 1,
}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202c;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-risk:#e05252;
      --hb-warn-bg:#3a2f10;--hb-warn-border:#7a6420;--hb-warn-ink:#f0d891}
body{margin:0;background:#0a1017}#host{width:740px;height:520px}
</style></head><body><div id="host"></div></body></html>"""

_MEASURE = """() => {
  const el = document.querySelector('.arx');
  if (!el) return {mounted: false};
  const vis = n => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const note = el.querySelector('.arx-note');
  const crumbs = [...el.querySelectorAll('.arx-crumb')];
  return {
    mounted: true,
    nested: el.querySelectorAll('.arx').length,
    rows: [...el.querySelectorAll('.arx-row .arx-nm')].map(n => n.textContent),
    row_meta: [...el.querySelectorAll('.arx-row .arx-meta')].map(n => n.textContent),
    icons: [...el.querySelectorAll('.arx-row .arx-ic')].map(n => n.textContent),
    tiles: [...el.querySelectorAll('.arx-tile .arx-nm')].map(n => n.textContent),
    crumbs: crumbs.map(b => b.textContent),
    crumb_last_disabled: crumbs.length ? crumbs[crumbs.length - 1].disabled : null,
    note_text: note ? note.textContent : '',
    note_visible: note ? vis(note) : false,
    note_warn: note ? note.classList.contains('warn') : false,
    providers: [...el.querySelectorAll('.arx-prov b')].map(n => n.textContent),
    tier_options: [...el.querySelectorAll('.arx-prov select option')].map(o => o.textContent),
    badges: [...el.querySelectorAll('.arx-badge')].map(n => n.textContent),
    footer: (el.querySelector('.arx-foot .arx-nm') || {}).textContent || '',
    injected_imgs: document.querySelectorAll('img').length,
    up_disabled: (el.querySelector('.arx-tools .arx-btn') || {}).disabled,
  };
}"""


def _run(steps):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 780, "height": 620})
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
            for data in steps:
                await pg.evaluate(
                    "d => window.render(document.getElementById('host'), d, {action: async () => ({ok:true})})",
                    data)
                await pg.wait_for_timeout(60)
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


@pytest.fixture(scope="module")
def plain(playwright_available):
    return _run([_BASE])[0]


def test_it_mounts_with_its_rows_and_no_page_errors(plain):
    assert plain["mounted"], "the explorer did not paint"
    assert plain["errors"] == [], plain["errors"]
    # `nested` counts .arx elements INSIDE the root one, so 0 is «not nested». A widget that re-renders into
    # its own subtree instead of at the root paints twice and detaches its handles, with no error (V2-124).
    assert plain["nested"] == 0, "the card must re-render at its ROOT, never inside itself (V2-124)"
    assert plain["rows"] == ["Contratos", "Contrato Axa.pdf"], plain["rows"]


def test_a_folder_and_a_file_are_told_apart_on_screen(plain):
    assert plain["icons"][0] == "📁", plain["icons"]
    assert plain["icons"][1] != "📁", "a PDF must not wear the folder icon"


def test_a_size_is_shown_only_when_there_is_one(plain):
    """A folder has no size and neither does a native Google document. «0 B» would be a false statement."""
    assert plain["row_meta"][0].strip() == "", plain["row_meta"]
    assert "1.5 KB" in plain["row_meta"][1], plain["row_meta"]


def test_the_breadcrumb_paints_and_the_place_you_are_in_is_not_a_link(plain):
    assert plain["crumbs"][0] in ("Mi unidad", "OneDrive"), plain["crumbs"]
    assert "Contratos" in plain["crumbs"]
    assert plain["crumb_last_disabled"] is True, "clicking where you already are should do nothing"


def test_AN_UNTRUSTED_FILE_NAME_STAYS_TEXT(playwright_available):
    """The one no source scan can settle. A file called `<img src=x onerror=…>` is legal in every provider."""
    nasty = '<img src=x onerror="window.__pwned=1">'
    hostile = {**_BASE, "entries": [{**_ENTRIES[1], "name": nasty}]}
    m = _run([hostile])[0]
    assert m["injected_imgs"] == 0, "the file name became an ELEMENT — that is stored XSS"
    assert m["rows"] == [nasty], "and it must still be READABLE as the text it is"
    assert m["errors"] == []


def test_the_reason_banner_is_VISIBLE_when_the_permission_cannot_list(playwright_available):
    """ok + zero entries + a reason. A banner with no height explains nothing, so height is what is asserted."""
    narrow = {**_BASE, "entries": [], "count": 0,
              "reason": "Le diste a zaelar el permiso «Solo los archivos que yo elija», que no puede listar carpetas."}
    m = _run([narrow])[0]
    assert m["note_visible"], "the reason has to be SEEN, not merely present in the DOM"
    assert m["note_warn"], "it is a warning, not a normal empty state"
    assert "no puede listar" in m["note_text"]


def test_an_empty_folder_and_a_narrow_permission_do_not_say_the_same_thing(playwright_available):
    empty = {**_BASE, "entries": [], "count": 0}
    m = _run([empty])[0]
    assert "vacía" in m["note_text"].lower(), m["note_text"]
    assert not m["note_warn"], "an empty folder is not a warning"


def test_grid_mode_paints_tiles_instead_of_rows(playwright_available):
    m = _run([{**_BASE, "mode": "grid"}])[0]
    assert m["tiles"] == ["Contratos", "Contrato Axa.pdf"], m["tiles"]
    assert m["rows"] == []


def test_selecting_a_file_shows_its_strip_with_the_link(playwright_available):
    m = _run([{**_BASE, "selected": _ENTRIES[1]}])[0]
    assert m["footer"] == "Contrato Axa.pdf", m["footer"]


def test_with_nothing_connected_the_card_offers_the_WIZARD_not_a_blank_list(playwright_available):
    off = {**_BASE, "connected": False, "entries": [], "trail": [],
           "providers": [{**_PROVIDERS[0], "connected": False}]}
    m = _run([off])[0]
    assert m["providers"] == ["Google Drive"], m["providers"]
    assert "lista para conectar" in " ".join(m["badges"]), m["badges"]
    assert "Solo los que elija" in m["tier_options"], (
        "the permission choice has to be visible BEFORE consenting, not discovered after the drive looks empty")


def test_a_provider_without_its_app_registered_says_where_to_register_it(playwright_available):
    off = {**_BASE, "connected": False, "entries": [], "trail": [],
           "providers": [{**_PROVIDERS[0], "connected": False, "app_configured": False}]}
    m = _run([off])[0]
    assert "Conectores" in m["note_text"], m["note_text"]
    assert m["tier_options"] == [], "there is nothing to choose until the app exists"
