"""A new card lands in the emptiest zone, at the size it will have (V2-773, operator's rule 2026-09-27).

«Cuando se coloca un nuevo widget busca hueco en la zona de la pantalla que está como más vacía y se van
intentando colocar de forma inteligente… y los botones que intentan autoposicionar los widgets, que todo eso
actúe contra el mismo motor de posicionamiento.» Measured before: a card was placed at a 400×340 loading tile,
then grew to its manifest size over its neighbours; the ⤢ button tiled against `innerHeight-150` with a private
320×240 floor. Three halves here: the pure engine (node), the real canvas in chromium (two declared-size cards
open without overlapping, and both bulk buttons keep every card whole and apart), and the catalogue (every card
widget declares a size and a minimum)."""
from __future__ import annotations

import json
import pathlib
import shutil
import socket
import subprocess
import sys
import time

import pytest

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = pathlib.Path(__file__).with_name("test_a_new_card_lands_in_the_emptiest_zone.mjs")
DESKTOP = _ENGINE / "frontend/app/widgets/desktop.js"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_engine_picks_the_emptiest_region():
    r = subprocess.run(["node", str(SCRIPT)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def test_every_automatic_placement_goes_through_the_one_engine():
    src = DESKTOP.read_text(encoding="utf-8")
    assert 'from "./placement.js' in src
    assert "_largestGap" not in src, "a second placement scan survived"
    place = src[src.index("_place(card, expected=null){"):src.index("_expected(baseId){")]
    assert "bestSpot({" in place and 'mode: "free"' in place
    compact = src[src.index("  compact(){"):src.index("  arrange(){")]
    assert "bestSpot({" in compact and 'mode:"tight"' in compact
    arrange = src[src.index("  arrange(){"):src.index("  // Live rects to avoid")]
    assert "innerHeight" not in arrange, "the ⤢ button tiles against a private bottom, not the canvas"
    assert "this._minSize(" in arrange and "Math.max(320" not in arrange, "a private floor instead of the widget's"
    assert "this._place(card, this._expected(baseId))" in src, "a fresh card is placed at a loading tile, not its size"
    assert "this._settle(w.card, id)" in src, "nothing re-checks the spot once the card has its real size"


def _card_widgets() -> list[tuple[str, dict]]:
    out = []
    for m in sorted((_ENGINE / "widgets").glob("*/manifest.json")):
        d = json.loads(m.read_text(encoding="utf-8"))
        if d.get("transient") or d.get("kind") == "backed" and d.get("id") == "navegador":
            continue
        out.append((m.parent.name, d))
    return out


def test_every_card_widget_declares_a_size_and_a_minimum_that_fit_each_other():
    missing = []
    for wid, d in _card_widgets():
        size, mn = d.get("size") or {}, d.get("min") or {}
        if not (size.get("w") and size.get("h") and mn.get("w") and mn.get("h")):
            missing.append(wid); continue
        assert 240 <= mn["w"] <= size["w"] and 150 <= mn["h"] <= size["h"], (wid, size, mn)
        assert 0.45 <= size["w"] / size["h"] <= 1.7, f"{wid} opens as a strip or a sliver: {size}"
    assert not missing, f"card widgets without a declared size+min: {missing}"


# ── the real canvas ────────────────────────────────────────────────────────────────────────────────────────────
pw_api = pytest.importorskip("playwright.sync_api")

_STUB_WIDGET = "export function render(el){ el.textContent = 'rendered'; }\nexport default { render };\n"
# «uno» is WIDE on purpose: on a 1200px desk (canvas 1172, so 703 is the 60% cap a fresh card may take) a
# 400×340 loading tile fits to its right and a 500px card does not — the exact shape of the incident (placed at
# the tile, grown over the neighbour). The others fit two abreast under it.
_SIZE = {"uno": {"w": 700, "h": 360}, "dos": {"w": 500, "h": 360}, "tres": {"w": 500, "h": 360}, "cuatro": {"w": 500, "h": 360}}
_REGISTRY = {"widgets": [{"id": w, "name": w.title(), "size": sz, "min": {"w": 300, "h": 240}} for w, sz in _SIZE.items()]}


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


@pytest.fixture(scope="module")
def page():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    from tests.waiting import port_listening
    port_listening(port)
    try:
        with pw_api.sync_playwright() as pw:
            browser = pw.chromium.launch()
            pg = browser.new_page(viewport={"width": 1200, "height": 900})
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))

            def _json(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
            pg.route("**/widgets", lambda r: _json(r, _REGISTRY))
            pg.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
            pg.route("**/widgets/*/widget.js", lambda r: r.fulfill(
                status=200, content_type="application/javascript", body=_STUB_WIDGET))
            pg.route("**/widgets/*/data*", lambda r: _json(r, {}))
            pg.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
            pg.route("**/api/**", lambda r: _json(r, {}))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async (port) => {
                document.body.innerHTML = '<div id="desk" style="position:fixed;inset:0"><div id="stage"></div></div><div id="activity"></div>';
                const m = await import(`http://127.0.0.1:${port}/frontend/app/widgets/desktop.js?v=1`);
                window.__desk = new m.Desktop(document.getElementById('stage'));
            }""", port)
            assert not errors, errors
            pg._hb_errors = errors
            yield pg
            browser.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _rects(page) -> dict[str, dict]:
    # offset* geometry: the desk coordinates the engine writes, untouched by the open animation's transform
    return page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('#stage .hb-win')].map(c =>
        [c.dataset.wid, {l:c.offsetLeft, t:c.offsetTop, r:c.offsetLeft+c.offsetWidth, b:c.offsetTop+c.offsetHeight,
                         w:c.offsetWidth, h:c.offsetHeight}]))""")


def _show(page, wid: str):
    page.evaluate("(id) => window.__desk.show(id, {data:{ok:true}})", wid)
    page.wait_for_selector(f"[data-wid='{wid}']:not(.loading)", timeout=8000)   # mounted, sized, settled
    page.wait_for_timeout(150)


def _apart(a, b, pad=12) -> bool:
    return a["r"] + pad <= b["l"] or a["l"] >= b["r"] + pad or a["b"] + pad <= b["t"] or a["t"] >= b["b"] + pad


def _assert_tidy(rects, canvas):
    ids = list(rects)
    for i, a in enumerate(ids):
        ra = rects[a]
        assert ra["l"] >= canvas["x0"] - 1 and ra["t"] >= canvas["y0"] - 1, (a, ra, canvas)
        assert ra["r"] <= canvas["x1"] + 1 and ra["b"] <= canvas["y1"] + 1, (a, ra, canvas)
        for b in ids[i + 1:]:
            assert _apart(ra, rects[b]), f"{a} and {b} overlap: {ra} / {rects[b]}"


def test_two_declared_size_cards_open_at_their_size_without_touching(page):
    """THE incident: placed at a 400×340 tile, grown to its declared size over the neighbour."""
    _show(page, "uno"); _show(page, "dos")
    rects, canvas = _rects(page), page.evaluate("() => window.__desk.canvas()")
    assert abs(rects["uno"]["w"] - 700) <= 4 and abs(rects["uno"]["h"] - 360) <= 4, rects["uno"]
    assert rects["dos"]["t"] >= rects["uno"]["b"] + 12, f"«dos» does not fit beside «uno» and went there anyway: {rects}"
    _assert_tidy(rects, canvas)
    assert not page._hb_errors, page._hb_errors


def test_the_third_card_goes_to_the_emptiest_region_not_the_first_pocket(page):
    """With «uno» across the top and «dos» under it, the strip right of «uno» is still too narrow: the emptiest
    region is beside «dos», and the third lands there — apart from both and whole."""
    _show(page, "tres")
    rects, canvas = _rects(page), page.evaluate("() => window.__desk.canvas()")
    _assert_tidy(rects, canvas)
    assert rects["tres"]["t"] >= rects["uno"]["b"] + 12 and rects["tres"]["l"] >= rects["dos"]["r"] + 12, rects


def test_both_bulk_buttons_keep_every_card_whole_and_apart(page):
    """The ▦ repack and the ⤢ fit-all act against the same canvas and the same floors as a fresh placement."""
    _show(page, "cuatro")
    page.set_viewport_size({"width": 1600, "height": 1000})   # a desk all four fit on, so «apart» is the whole claim
    page.wait_for_timeout(200)
    page.evaluate("() => window.__desk.compact()")
    page.wait_for_timeout(100)
    _assert_tidy(_rects(page), page.evaluate("() => window.__desk.canvas()"))
    page.evaluate("() => window.__desk.arrange()")
    page.wait_for_timeout(100)
    rects, canvas = _rects(page), page.evaluate("() => window.__desk.canvas()")
    _assert_tidy(rects, canvas)
    for wid, r in rects.items():
        assert r["w"] >= 300 and r["h"] >= 240, (wid, r)          # the widget's own floor, never below
        assert r["b"] <= canvas["y1"] + 1, f"{wid} tiled below the canvas: {r} vs {canvas}"
    assert not page._hb_errors, page._hb_errors


def test_a_lone_card_is_never_blown_up_to_the_whole_desk(page):
    """Demo pass 2026-09-28 (full14 C5b): «tidy up the screen» with ONE card open — the cell was the whole desk,
    and the monitor results became a full-screen wall every later card (photos, map, chart) landed on, 100%
    overlapped. A cell shrinks a card to fit; it never grows one past its own size."""
    for wid in ("dos", "tres", "cuatro"):
        page.evaluate("(id) => window.__desk.close(id)", wid)
    page.wait_for_timeout(150)
    before = _rects(page)["uno"]
    page.evaluate("() => window.__desk.arrange()")
    page.wait_for_timeout(100)
    after, canvas = _rects(page)["uno"], page.evaluate("() => window.__desk.canvas()")
    assert after["w"] <= before["w"] + 4 and after["h"] <= before["h"] + 4, (before, after, canvas)
    assert not page._hb_errors, page._hb_errors
