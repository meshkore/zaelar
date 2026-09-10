"""V2-658 — the file manager RENDERED: the local shelves, a cloud folder, the provider chips, and the XSS
surface. Rendering is the only way to check the half that matters here — three things no source read can settle:

  · A file name is UNTRUSTED text — a cloud drive's, or a file the operator (or a torrent) named. `<img
    src=x onerror=…>` is a legal file name everywhere it can come from. Only a browser can say whether that
    became an element or stayed a string.
  · The connect wizard is REQUESTED now, never forced by "nothing connected" — local needs no connection, so
    a disconnected cloud provider must not paper over the whole card with a wizard nobody asked to see.
  · A cloud row's per-file actions are exactly "open the link" — rename/copy/delete must not even be DRAWN for
    a provider that cannot do them, matching the operator's own framing (the connector's limit, not the widget's).

It also guards the V2-124 shape: re-rendering at the ROOT rather than nesting the widget inside its own subtree.
"""
from __future__ import annotations

import asyncio
import os

import pytest

ENG = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
_WIDGET = os.path.join(ENG, "widgets", "archivos", "widget.js")

_SHELVES = [
    {"id": f"shelf:{k}", "name": n, "kind": "folder", "mime": "", "size": None, "modified": "",
     "provider": "local", "count": c}
    for k, n, c in [("video", "Vídeo", 3), ("audio", "Audio", 0), ("documents", "Documentos", 2),
                    ("images", "Imágenes", 5), ("downloads", "Descargas", 0)]
]

_LOCAL_FILES = [
    {"id": "documents/factura.pdf", "name": "factura.pdf", "kind": "file", "file_kind": "document",
     "mime": "application/pdf", "size": 1536, "modified": "2026-01-02T10:00:00Z", "provider": "local",
     "playable": True, "url": "/api/library/stream?path=documents/factura.pdf",
     "download_url": "/api/library/download?path=documents/factura.pdf"},
    {"id": "documents/viejo.docx", "name": "viejo.docx", "kind": "file", "file_kind": "document",
     "mime": "application/octet-stream", "size": 2048, "modified": "2025-11-02T10:00:00Z", "provider": "local",
     "playable": False, "url": "", "download_url": "/api/library/download?path=documents/viejo.docx"},
]

_CLOUD_FILES = [
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
    "provider": "local", "providers": _PROVIDERS, "providers_stale": False, "connected": True,
    "folder_id": "", "trail": [], "entries": _SHELVES, "next": "", "query": "", "selected": None,
    "mode": "list", "panel": "", "error": "", "reason": "", "count": 5, "needs_refresh": False, "updated": 1,
}

_HTML = """<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{--hb-bg:#0f1720;--hb-bg-soft:#16202c;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-risk:#e05252;
      --hb-warn-bg:#3a2f10;--hb-warn-border:#7a6420;--hb-warn-ink:#f0d891}
body{margin:0;background:#0a1017}#host{width:820px;height:600px}
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
    shelves: [...el.querySelectorAll('.arx-shelf b')].map(n => n.textContent),
    rows: [...el.querySelectorAll('.arx-row .arx-nm')].map(n => n.textContent),
    row_meta: [...el.querySelectorAll('.arx-row .arx-meta')].map(n => n.textContent),
    icons: [...el.querySelectorAll('.arx-row .arx-ic')].map(n => n.textContent),
    tiles: [...el.querySelectorAll('.arx-tile .arx-nm')].map(n => n.textContent),
    row_action_counts: [...el.querySelectorAll('.arx-row')].map(r => r.querySelectorAll('.arx-ac').length),
    crumbs: crumbs.map(b => b.textContent),
    crumb_last_disabled: crumbs.length ? crumbs[crumbs.length - 1].disabled : null,
    note_text: note ? note.textContent : '',
    note_visible: note ? vis(note) : false,
    note_warn: note ? note.classList.contains('warn') : false,
    providers: [...el.querySelectorAll('.arx-prov b')].map(n => n.textContent),
    tier_options: [...el.querySelectorAll('.arx-prov select option')].map(o => o.textContent),
    badges: [...el.querySelectorAll('.arx-badge')].map(n => n.textContent),
    footer: (el.querySelector('.arx-foot .arx-nm') || {}).textContent || '',
    pchips: [...el.querySelectorAll('.arx-pchip')].map(n => ({t: n.textContent, on: n.classList.contains('on'),
             conn: n.classList.contains('conn'), off: n.classList.contains('off')})),
    injected_imgs: document.querySelectorAll('img').length,
    up_disabled: (el.querySelector('.arx-tools .arx-btn') || {}).disabled,
  };
}"""


def _run(steps):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 860, "height": 700})
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
def home(playwright_available):
    return _run([_BASE])[0]


def test_it_mounts_on_the_local_shelves_by_default_with_no_page_errors(home):
    assert home["mounted"], "the explorer did not paint"
    assert home["errors"] == [], home["errors"]
    assert home["nested"] == 0, "the card must re-render at its ROOT, never inside itself (V2-124)"
    assert home["shelves"] == ["Vídeo", "Audio", "Documentos", "Imágenes", "Descargas"], home["shelves"]


def test_the_provider_row_shows_local_as_active_and_the_cloud_chip_as_connected(home):
    local = next(c for c in home["pchips"] if c["t"] == "💻")
    assert local["on"] is True
    cloud = [c for c in home["pchips"] if c["t"] != "💻"]
    assert cloud and cloud[0]["conn"] is True and cloud[0]["on"] is False


def test_an_unconnected_cloud_provider_reads_OFF_and_local_still_works(playwright_available):
    off = {**_BASE, "providers": [{**_PROVIDERS[0], "connected": False}]}
    m = _run([off])[0]
    cloud = [c for c in m["pchips"] if c["t"] != "💻"]
    assert cloud and cloud[0]["off"] is True
    assert m["shelves"], "local browsing must not depend on any cloud connection"


def test_the_connect_panel_shows_ONLY_when_requested_never_forced_by_a_disconnected_cloud(playwright_available):
    off = {**_BASE, "providers": [{**_PROVIDERS[0], "connected": False}]}
    m = _run([off])[0]
    assert m["providers"] == [], "no wizard content without panel:'connect' — local needs no connection"
    requested = {**off, "panel": "connect"}
    m2 = _run([requested])[0]
    assert m2["providers"] == ["Google Drive"], m2["providers"]


def test_a_local_folder_lists_its_files_with_size_and_action_icons(playwright_available):
    local_folder = {**_BASE, "folder_id": "shelf:documents",
                    "trail": [{"id": "shelf:documents", "name": "Documentos"}], "entries": _LOCAL_FILES, "count": 2}
    m = _run([local_folder])[0]
    assert m["rows"] == ["factura.pdf", "viejo.docx"], m["rows"]
    assert "1.5 KB" in m["row_meta"][0]
    # a local file row carries open + rename + copy + delete = 4 action icons
    assert m["row_action_counts"] == [4, 4], m["row_action_counts"]


def test_a_cloud_folder_offers_only_the_open_link_never_rename_copy_or_delete(playwright_available):
    cloud_folder = {**_BASE, "provider": "gdrive", "folder_id": "d1",
                    "trail": [{"id": "d1", "name": "Contratos"}], "entries": _CLOUD_FILES, "count": 2}
    m = _run([cloud_folder])[0]
    assert m["rows"] == ["Contratos", "Contrato Axa.pdf"], m["rows"]
    # the FOLDER row carries no per-file actions at all (0); the FILE row carries exactly the "open link" icon
    assert m["row_action_counts"] == [0, 1], m["row_action_counts"]


def test_a_folder_and_a_file_are_told_apart_on_screen(playwright_available):
    cloud_folder = {**_BASE, "provider": "gdrive", "folder_id": "d1",
                    "trail": [{"id": "d1", "name": "Contratos"}], "entries": _CLOUD_FILES, "count": 2}
    m = _run([cloud_folder])[0]
    assert m["icons"][0] == "📁", m["icons"]
    assert m["icons"][1] != "📁", "a PDF must not wear the folder icon"


def test_the_breadcrumb_paints_and_the_place_you_are_in_is_not_a_link(playwright_available):
    cloud_folder = {**_BASE, "provider": "gdrive", "folder_id": "d1",
                    "trail": [{"id": "d1", "name": "Contratos"}], "entries": _CLOUD_FILES, "count": 2}
    m = _run([cloud_folder])[0]
    assert "Mi unidad" in m["crumbs"] or "OneDrive" in m["crumbs"], m["crumbs"]
    assert "Contratos" in m["crumbs"]
    assert m["crumb_last_disabled"] is True, "clicking where you already are should do nothing"


def test_AN_UNTRUSTED_FILE_NAME_STAYS_TEXT(playwright_available):
    """The one no source scan can settle. A file called `<img src=x onerror=…>` is a legal name."""
    nasty = '<img src=x onerror="window.__pwned=1">'
    hostile = {**_BASE, "folder_id": "shelf:documents",
               "trail": [{"id": "shelf:documents", "name": "Documentos"}],
               "entries": [{**_LOCAL_FILES[0], "name": nasty}], "count": 1}
    m = _run([hostile])[0]
    assert m["injected_imgs"] == 0, "the file name became an ELEMENT — that is stored XSS"
    assert m["rows"] == [nasty], "and it must still be READABLE as the text it is"
    assert m["errors"] == []


def test_the_reason_banner_is_VISIBLE_when_a_cloud_permission_cannot_list(playwright_available):
    narrow = {**_BASE, "provider": "gdrive", "entries": [], "count": 0,
              "reason": "Le diste a zaelar el permiso «Solo los archivos que yo elija», que no puede listar carpetas."}
    m = _run([narrow])[0]
    assert m["note_visible"], "the reason has to be SEEN, not merely present in the DOM"
    assert m["note_warn"], "it is a warning, not a normal empty state"
    assert "no puede listar" in m["note_text"]


def test_an_empty_local_folder_says_empty_not_a_warning(playwright_available):
    empty = {**_BASE, "folder_id": "shelf:audio",
             "trail": [{"id": "shelf:audio", "name": "Audio"}], "entries": [], "count": 0}
    m = _run([empty])[0]
    assert "vacía" in m["note_text"].lower(), m["note_text"]
    assert not m["note_warn"], "an empty folder is not a warning"


def test_grid_mode_paints_tiles_instead_of_rows(playwright_available):
    m = _run([{**_BASE, "provider": "gdrive", "folder_id": "d1",
               "trail": [{"id": "d1", "name": "Contratos"}], "entries": _CLOUD_FILES, "count": 2,
               "mode": "grid"}])[0]
    assert m["tiles"] == ["Contratos", "Contrato Axa.pdf"], m["tiles"]
    assert m["rows"] == []


def test_selecting_a_cloud_file_shows_its_strip_with_the_link(playwright_available):
    m = _run([{**_BASE, "provider": "gdrive", "selected": _CLOUD_FILES[1]}])[0]
    assert m["footer"] == "Contrato Axa.pdf", m["footer"]


def test_a_provider_without_its_app_registered_says_where_to_register_it(playwright_available):
    off = {**_BASE, "panel": "connect",
           "providers": [{**_PROVIDERS[0], "connected": False, "app_configured": False}]}
    m = _run([off])[0]
    assert "Conectores" in m["note_text"], m["note_text"]
    assert m["tier_options"] == [], "there is nothing to choose until the app exists"
