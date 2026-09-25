"""The image viewer OPENS with everything in view: the photo, and the whole strip of thumbnails under it.

The operator, 2026-09-25, with a screenshot of the card as it opened: *«es de imágenes pero no se ven las
miniaturas de abajo… necesitamos que los widgets se abran en su tamaño mínimo por defecto para que se vean
todas las opciones y tal y como han sido concebidos»* — and then: *«las miniaturas… crecen hasta el infinito
hacia la derecha… para verlas todas tengo que ampliar el ancho del widget y eso no es correcto. Igual que la
imagen se adapta, el espacio para miniaturas también»*.

Measured before the fix: the stage was a FIXED `min(52vh,380px)` and the card is capped at 82vh, so on a laptop
the strip fell below the card's edge; and the card sized itself to its content, so twelve thumbnails made it as
wide as all twelve. Rendered here on the REAL canvas (`desktop.js`) with the REAL widget, on a laptop viewport.
"""
from __future__ import annotations

import json
import pathlib
import socket
import subprocess
import sys
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
_MANIFEST = json.loads((_ENGINE / "widgets/imagenes/manifest.json").read_text(encoding="utf-8"))
_PIX = ("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='200'>"
        "<rect width='300' height='200' fill='%23c33'/></svg>")
_ITEMS = [{"title": f"Lotus Esprit {k}", "url": _PIX, "thumb": _PIX, "site": "es.wikipedia.org",
           "w": 2983, "h": 1352} for k in range(1, 13)]


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close()
    return p


@pytest.fixture(scope="module")
def viewer():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    index = {"widgets": [{k: _MANIFEST[k] for k in ("id", "name", "title", "size", "fullscreen") if k in _MANIFEST}]}
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_page(viewport={"width": 1280, "height": 650})      # a laptop, the screen he saw it on
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg._calls = []

            def _json(route, payload):
                route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

            def _action(route):
                pg._calls.append(route.request.post_data)
                _json(route, {"ok": True})
            pg.route("**/api/**", lambda r: _json(r, {}))
            pg.route("**/widgets/registry", lambda r: _json(r, {"registry": []}))
            pg.route("**/widgets", lambda r: _json(r, index))
            pg.route("**/widgets/imagenes/data*", lambda r: _json(r, {"items": _ITEMS, "i": 0, "n": 12,
                                                                     "query": "lotus esprit"}))
            pg.route("**/widgets/imagenes/action*", _action)
            pg.route("**/widgets/*/aliases*", lambda r: _json(r, {"ok": True, "aliases": []}))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.evaluate("""async (port) => {
                document.body.innerHTML = '<div id="stage" style="position:fixed;inset:0"></div><div id="activity"></div>';
                const m = await import(`http://127.0.0.1:${port}/frontend/app/widgets/desktop.js?v=1`);
                window.__desk = new m.Desktop(document.getElementById('stage'));
                await window.__desk.show('imagenes', {});
            }""", port)
            pg.wait_for_selector("[data-wid='imagenes'] .imgthumb", timeout=8000)
            pg.wait_for_timeout(700)
            pg._errors = errors
            yield pg
            b.close()
    finally:
        srv.terminate(); srv.wait(timeout=10)


def _geom(pg):
    return pg.evaluate("""() => {
        const card = document.querySelector("[data-wid='imagenes']");
        const strip = card.querySelector('.imgstrip'), stage = card.querySelector('.imgstage');
        const r = e => e.getBoundingClientRect();
        const sc = card.querySelector('.hb-scroll');
        return {cardW: r(card).width, cardH: r(card).height, cardBottom: r(card).bottom, cardRight: r(card).right,
                vw: innerWidth, vh: innerHeight, stripBottom: r(strip).bottom, stripW: strip.clientWidth,
                stripScrollW: strip.scrollWidth, stageH: r(stage).height,
                cardScrolls: sc ? sc.scrollHeight > sc.clientHeight + 1 : false,
                scrollBar: getComputedStyle(strip).scrollbarWidth}; }""")


def test_the_card_opens_with_the_strip_on_screen_without_scrolling(viewer):
    g = _geom(viewer)
    assert g["cardBottom"] <= g["vh"] and g["cardH"] <= g["vh"], f"the card runs off a laptop screen: {g}"
    assert g["stripBottom"] <= g["cardBottom"] - 4, f"the thumbnails are below the card's edge: {g}"
    assert not g["cardScrolls"], f"he has to scroll the card to find the thumbnails: {g}"
    assert g["stageH"] >= 140, f"the photo was squeezed to nothing to make room: {g}"


def test_twelve_thumbnails_never_widen_the_card(viewer):
    """The strip is as wide as the card and scrolls — the card is not as wide as the strip."""
    g = _geom(viewer)
    assert g["cardW"] <= 560 and g["cardRight"] <= g["vw"], f"the card grew to fit the thumbnails: {g}"
    assert g["stripScrollW"] > g["stripW"] + 10, f"twelve thumbnails did not overflow into a scroll: {g}"


def test_the_mouse_wheel_moves_the_strip_sideways(viewer):
    """A mouse has no horizontal wheel: without this the twelfth photo needed a wider card."""
    viewer.evaluate("() => { document.querySelector('.imgstrip').scrollLeft = 0; }")
    box = viewer.locator(".imgstrip").bounding_box()
    viewer.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    viewer.mouse.wheel(0, 300)
    viewer.wait_for_timeout(250)
    assert viewer.evaluate("() => document.querySelector('.imgstrip').scrollLeft") > 50


def test_the_strip_can_be_dragged_and_a_drag_is_not_a_click(viewer):
    viewer.evaluate("() => { document.querySelector('.imgstrip').scrollLeft = 0; }")
    viewer._calls.clear()
    box = viewer.locator(".imgstrip").bounding_box()
    y = box["y"] + box["height"] / 2
    viewer.mouse.move(box["x"] + box["width"] - 40, y)
    viewer.mouse.down()
    viewer.mouse.move(box["x"] + 60, y, steps=8)
    viewer.mouse.up()
    viewer.wait_for_timeout(250)
    assert viewer.evaluate("() => document.querySelector('.imgstrip').scrollLeft") > 50, "the drag did not scroll"
    assert not viewer._calls, f"the drag selected a photo on release: {viewer._calls}"


def test_no_script_error(viewer):
    assert not viewer._errors, viewer._errors
