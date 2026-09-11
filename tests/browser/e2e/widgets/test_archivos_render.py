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

def _html(host_w=820, host_h=600):
    # The card's OWN box, not the viewport, is what `ensureTierObserver` measures — real cards resize
    # independently of the browser window (the operator drags a card, never the whole app). Parametrized so
    # tier-boundary tests can grow/shrink `#host` directly instead of faking it with the viewport.
    return f"""<!doctype html><html data-theme="dark"><head><meta charset="utf-8"><style>
:root{{--hb-bg:#0f1720;--hb-bg-soft:#16202c;--hb-ink:#e8eef6;--hb-muted:#9fb0c4;--hb-muted-2:#6f8299;
      --hb-line:#243244;--hb-accent:#2F6FEB;--hb-accent2:#16B8A6;--hb-risk:#e05252;
      --hb-warn-bg:#3a2f10;--hb-warn-border:#7a6420;--hb-warn-ink:#f0d891}}
body{{margin:0;background:#0a1017}}#host{{width:{host_w}px;height:{host_h}px}}
</style></head><body><div id="host"></div></body></html>"""


_HTML = _html()

_MEASURE = """() => {
  const el = document.querySelector('.arx');
  if (!el) return {mounted: false};
  const vis = n => { const r = n.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const note = el.querySelector('.arx-note');
  const crumbs = [...el.querySelectorAll('.arx-crumb')];
  return {
    mounted: true,
    nested: el.querySelectorAll('.arx').length,
    tier: el.dataset.tier || '',
    shelves: [...el.querySelectorAll('.arx-shelf b')].map(n => n.textContent),
    rows: [...el.querySelectorAll('.arx-row .arx-nm')].map(n => n.textContent),
    row_meta: [...el.querySelectorAll('.arx-row .arx-meta')].map(n => n.textContent),
    row_loc: [...el.querySelectorAll('.arx-row .arx-col-loc')].map(n => vis(n) ? n.textContent : ''),
    icons: [...el.querySelectorAll('.arx-row .arx-ic')].map(n => n.textContent),
    tiles: [...el.querySelectorAll('.arx-tile .arx-nm')].map(n => n.textContent),
    row_action_counts: [...el.querySelectorAll('.arx-row')].map(r => r.querySelectorAll('.arx-ac').length),
    crumbs: crumbs.map(b => b.textContent),
    crumb_last_disabled: crumbs.length ? crumbs[crumbs.length - 1].disabled : null,
    crumb_more: !!el.querySelector('.arx-crumb-more'),
    search_tag: (el.querySelector('.arx-tag') || {}).textContent || '',
    find_value: (el.querySelector('.arx-find input') || {}).value ?? null,
    find_has_x: !!el.querySelector('.arx-find-x'),
    note_text: note ? note.textContent : '',
    note_visible: note ? vis(note) : false,
    note_warn: note ? note.classList.contains('warn') : false,
    providers: [...el.querySelectorAll('.arx-prov b')].map(n => n.textContent),
    tier_options: [...el.querySelectorAll('.arx-prov select option')].map(o => o.textContent),
    badges: [...el.querySelectorAll('.arx-badge')].map(n => n.textContent),
    footer: (el.querySelector('.arx-foot .arx-nm') || {}).textContent || '',
    pchips: [...el.querySelectorAll('.arx-pchip')].map(n => ({t: n.textContent, on: n.classList.contains('on'),
             conn: n.classList.contains('conn'), off: n.classList.contains('off')})),
    side_items: [...el.querySelectorAll('.arx-side-item .arx-side-nm')].map(n => n.textContent),
    side_visible: (() => { const s = el.querySelector('.arx-side'); return s ? vis(s) : false; })(),
    cx_close_visible: (() => { const c = document.querySelector('.arx-cxclose'); return c ? vis(c) : false; })(),
    injected_imgs: document.querySelectorAll('img').length,
    up_disabled: (el.querySelector('.arx-tools .arx-btn') || {}).disabled,
  };
}"""


def _run(steps, width=860, height=700, host_w=820, host_h=600):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": width, "height": height})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            async def _page(route):
                await route.fulfill(status=200, content_type="text/html", body=_html(host_w, host_h))
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
                await pg.wait_for_timeout(80)
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


# ── V2-662: navigation clarity — the sidebar, ONE search field, and an exit from the connect screen ─────────
# The operator's own report: landing in a search or a cloud folder with no sense of where he was, two boxes
# both showing the query, and getting trapped in the connect panel with no way back out.

def test_a_narrow_card_hides_the_sidebar_and_a_wide_one_shows_the_shelves_and_every_service(playwright_available):
    narrow = _run([_BASE], host_w=500)[0]
    assert narrow["tier"] == "s", narrow["tier"]
    assert narrow["side_visible"] is False, "a small card has no room for a sidebar — everything stays central"

    wide = _run([_BASE], host_w=1000)[0]
    assert wide["tier"] == "l", wide["tier"]
    assert wide["side_visible"] is True
    assert wide["side_items"][:5] == ["Vídeo", "Audio", "Documentos", "Imágenes", "Descargas"], wide["side_items"]
    assert "Google Drive" in wide["side_items"], "the sidebar is a SECOND way to the same places, not a smaller one"


def test_the_search_field_is_the_only_place_the_query_lives_no_duplicate_box(playwright_available):
    hits = [{**_LOCAL_FILES[0], "shelf": "documents"}]
    searching = {**_BASE, "folder_id": "", "trail": [], "query": "factura", "entries": hits, "count": 1}
    m = _run([searching])[0]
    assert m["find_value"] == "factura", "the query lives in the search INPUT, nowhere else"
    assert m["find_has_x"] is True, "a live search always offers its own clear button, right beside the text"
    assert m["search_tag"] == "1 resultado", m["search_tag"]
    # the breadcrumb never repeats the query as a fake crumb — that was the second box the operator saw
    assert not any("factura" in (c or "") for c in m["crumbs"]), m["crumbs"]
    assert not any("Resultados" in (c or "") for c in m["crumbs"]), m["crumbs"]


def test_a_mixed_search_names_which_shelf_each_hit_lives_on(playwright_available):
    hits = [{**_LOCAL_FILES[0], "shelf": "documents"}, {**_LOCAL_FILES[1], "shelf": "documents"}]
    searching = {**_BASE, "provider": "local", "query": "algo", "entries": hits, "count": 2}
    at_small = _run([searching], host_w=500)[0]
    assert all(t == "" for t in at_small["row_loc"]), \
        "the shelf column is a WIDE-card affordance, not clutter on a phone-ish card"
    at_large = _run([searching], host_w=1000)[0]
    assert all("Documentos" in (t or "") for t in at_large["row_loc"]), at_large["row_loc"]


def test_a_long_cloud_trail_collapses_and_the_ellipsis_expands_it(playwright_available):
    deep_trail = [{"id": f"d{i}", "name": f"Carpeta {i}"} for i in range(6)]
    deep = {**_BASE, "provider": "gdrive", "folder_id": "d5", "trail": deep_trail, "entries": _CLOUD_FILES}
    collapsed = _run([deep])[0]
    assert collapsed["crumb_more"] is True, "six levels deep must not print six crumbs"
    assert "Carpeta 0" not in collapsed["crumbs"], "the buried early steps are the ones that hide"
    assert "Carpeta 5" in collapsed["crumbs"], "the current location always stays visible"
    assert collapsed["crumb_last_disabled"] is True

    shallow_trail = deep_trail[:2]
    shallow = {**deep, "folder_id": "d1", "trail": shallow_trail}
    m2 = _run([shallow])[0]
    assert m2["crumb_more"] is False, "a short trail never collapses — nothing to hide"


def test_the_connect_screens_close_button_is_reachable_without_scrolling(playwright_available):
    m = _run([{**_BASE, "panel": "connect"}])[0]
    assert m["cx_close_visible"] is True, "landing here must never trap the operator with no way back"
