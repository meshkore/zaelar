"""A scroller starts below its header, and nothing shows through it (V2-821, RENDERED).

The operator, cloud agent build 77: scrolling the results sheet, the list moved BEHIND the card's header and the
sheet's tab bar (Proceso / Resultado / Sumario…) and showed through them — a line «canal, email, no, whatsapp» from
the list peeking above the tabs. The mechanism: the sheet's header was position:sticky against the CARD's scroller,
and that scroller is padded, so sticky held the header at the content edge and the padding band above it was a
window the list scrolled through; the tabs' bottom margin was a second, transparent band.

The fix is structural: a header that must stay put is not in the scroller. The sheet is a flex column — a fixed
header band and ONE scroller (the panel, declared with data-hb-scroller so both hosts' ctx.top()/ctx.scroll() move
it). This mounts the real widget inside each host's REAL card CSS (desktop.js and the phone's Deck.js, read from
the source), scrolls a long list the way the operator does (the wheel), and asserts what the eye sees:

  · the element that scrolled starts at or below the tab bar's bottom edge;
  · no list element has a VISIBLE box (clipped by every scrolling ancestor) over the header band;
  · hit-testing the header band never lands on the list;
  · the card's own scroller no longer scrolls behind the panel;
  · a data refresh keeps the operator where he was reading.

Set V2_821_SHOTS=<dir> to also save a screenshot of each host after the scroll.
"""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys

import pytest
from tests.waiting import port_listening, until_sync

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright

_ENGINE = pathlib.Path(__file__).resolve().parents[4]


def _host_css(rel: str, marker: str) -> str:
    """The CSS a host injects, read from its source: the test fails with the host, not with a copy of it."""
    src = (_ENGINE / rel).read_text(encoding="utf-8")
    i = src.index(marker)
    a = src.index("`", i) + 1
    return src[a:src.index("`", a)]


_PALETTE = '<link rel="stylesheet" href="/frontend/app/core/palette.css">'

_DESK = """<!doctype html><html><head><meta charset="utf-8">%s<style>body{margin:0;background:var(--canvas,#101216)}
%s</style></head><body>
<div class="hb-stage"><div class="hb-win in" style="left:24px;top:24px;width:720px;height:560px">
  <div class="hb-head"><div class="hb-wicon">R</div><button class="hb-name">results</button></div>
  <div class="hb-scroll"><div class="hb-body" id="w" data-host-title="1"></div></div>
</div></div></body></html>"""

_DECK = """<!doctype html><html><head><meta charset="utf-8">%s<style>:root{--dock-h:64px}body{margin:0}
%s</style></head><body>
<div class="zm-deck"><div class="zm-card live">
  <div class="zm-head"><div class="zm-ttl"><div class="zm-title">results</div></div></div>
  <div class="zm-scroll"><div class="zm-body" id="w"></div></div>
</div></div></body></html>"""

_HOSTS = {
    # name: (viewport, page, card selector, card scroller selector)
    "desktop": ({"width": 900, "height": 700},
                lambda: _DESK % (_PALETTE, _host_css("frontend/app/widgets/desktop.js", 's.id="hb-desk-css"')),
                ".hb-win", ".hb-scroll"),
    "phone375": ({"width": 375, "height": 760},
                 lambda: _DECK % (_PALETTE, _host_css("frontend/mobile/app/shell/Deck.js", 's.id = "zm-deck-css"')),
                 ".zm-card", ".zm-scroll"),
}


def _data():
    items = [{"title": f"Fontanero {i} — canal, email, no, whatsapp", "price": f"{40 + i} €",
              "url": f"https://example.com/{i}", "snippet": "canal, email, no, whatsapp · " * 3}
             for i in range(36)]
    return {"title": "Fontaneros en Madrid", "subtitle": "36 resultados · ordenados por valoración",
            "items": items, "tab": "results"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def _browser():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=_ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    port_listening(port)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            browser._hb_base = f"http://127.0.0.1:{port}"
            yield browser
            browser.close()
    finally:
        srv.terminate()


def _mount(browser, host):
    viewport, page_html, card_sel, _ = _HOSTS[host]
    page = browser.new_page(viewport=viewport)
    page.goto(browser._hb_base + "/widgets/results/")
    page.set_content(page_html())
    page.evaluate(
        """async ([src, data]) => {
             const mod = await import(src);
             window.__render = (d) => mod.render(document.getElementById('w'), d,
               { action: () => Promise.resolve(null), top: () => {}, scroll: () => {}, t: null });
             window.__render(data);
           }""",
        [browser._hb_base + "/widgets/results/widget.js", _data()],
    )
    until_sync(lambda: page.locator(".hr-card").count() >= 20, "the long list (a page of it) to be painted")
    box = page.locator(card_sel).bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.7)
    page.mouse.wheel(0, 420)
    until_sync(lambda: page.evaluate(_SCROLLED_JS) > 0, "the wheel to scroll the sheet")
    return page


# The element that actually scrolled: the nearest scrolling ancestor of the list with a non-zero offset.
_SCROLLED_JS = """(() => { let n = document.querySelector('.hr-card');
  for (; n; n = n.parentElement) if (n.scrollTop > 0) return n.scrollTop; return 0; })()"""

_GEOMETRY_JS = """(cardSel) => {
  const card = document.querySelector(cardSel);
  const tabs = document.querySelector('.hr-tabs').getBoundingClientRect();
  let scroller = null;
  for (let n = document.querySelector('.hr-card'); n && n !== card; n = n.parentElement)
    if (n.scrollTop > 0) { scroller = n; break; }
  // A list element's VISIBLE box: its rect clipped by every ancestor that clips overflow.
  const visible = (el) => {
    let r = el.getBoundingClientRect(), top = r.top, bottom = r.bottom, left = r.left, right = r.right;
    for (let a = el.parentElement; a; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.overflowY === 'visible' && cs.overflowX === 'visible') continue;
      const q = a.getBoundingClientRect();
      top = Math.max(top, q.top); bottom = Math.min(bottom, q.bottom);
      left = Math.max(left, q.left); right = Math.min(right, q.right);
    }
    return {top, bottom, h: bottom - top, w: right - left};
  };
  const cardTop = card.getBoundingClientRect().top;
  const over = [];
  for (const el of document.querySelectorAll('.hr-panel .hr-card')) {
    const v = visible(el);
    if (v.h > 0.5 && v.w > 0.5 && v.top < tabs.bottom - 0.5)
      over.push([el.textContent.slice(0, 40), Math.round(v.top), Math.round(v.bottom)]);
  }
  // Hit-test the header band — from the card's top edge down to the tab line — across the whole width.
  const r = card.getBoundingClientRect(), hits = [];
  for (let y = cardTop + 2; y < tabs.bottom - 1; y += 4)
    for (let x = r.left + 6; x < r.right - 6; x += 24) {
      const e = document.elementFromPoint(x, y);
      if (e && e.closest('.hr-panel')) { hits.push([Math.round(x), Math.round(y), e.className]); break; }
    }
  const chrome = card.querySelector(':scope > .hb-scroll, :scope > .zm-scroll');
  return {scrollerTop: scroller ? scroller.getBoundingClientRect().top : null,
          scrollerIsPanel: !!(scroller && scroller.matches('[data-hb-scroller]')),
          tabsBottom: tabs.bottom, over, hits,
          chromeScrolls: chrome.scrollHeight - chrome.clientHeight};
}"""


@pytest.mark.parametrize("host", list(_HOSTS))
def test_a_scrolled_list_never_shows_through_the_header(_browser, host):
    page = _mount(_browser, host)
    try:
        g = page.evaluate(_GEOMETRY_JS, _HOSTS[host][2])
        shots = os.environ.get("V2_821_SHOTS")
        if shots:
            pathlib.Path(shots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(pathlib.Path(shots) / f"{host}.png"))
        assert not g["over"], f"list elements visible over the header band: {g['over']}"
        assert not g["hits"], f"the header band hit-tests onto the list: {g['hits']}"
        assert g["scrollerTop"] is not None, "something scrolled, and it is an ancestor of the list"
        assert g["scrollerTop"] >= g["tabsBottom"] - 0.5, (
            f"the scroller starts at {g['scrollerTop']:.1f}px, above the tab bar's bottom ({g['tabsBottom']:.1f}px): "
            "the list scrolls behind the header")
        assert g["scrollerIsPanel"], "the sheet's one scroller is the panel it declares (data-hb-scroller)"
        assert g["chromeScrolls"] <= 0, "the card's own scroller must not scroll behind the panel"
    finally:
        page.close()


@pytest.mark.parametrize("host", list(_HOSTS))
def test_a_data_refresh_keeps_him_where_he_was_reading(_browser, host):
    page = _mount(_browser, host)
    try:
        before = page.evaluate(_SCROLLED_JS)
        data = _data()
        data["items"].append({"title": "Fontanero nuevo", "price": "39 €", "url": "https://example.com/new"})
        page.evaluate("(d) => window.__render(d)", data)
        assert page.evaluate(_SCROLLED_JS) == before, "a worker append must not move what he is reading"
    finally:
        page.close()


def test_both_hosts_move_the_scroller_the_widget_declares():
    """ctx.top()/ctx.scroll() are host chrome (V2-591): a host that kept moving its own scroller would leave a
    sheet with a fixed header unscrollable by voice and stuck mid-list after a tab change."""
    desk = (_ENGINE / "frontend/app/widgets/desktop.js").read_text(encoding="utf-8")
    deck = (_ENGINE / "frontend/mobile/app/shell/Deck.js").read_text(encoding="utf-8")
    assert "[data-hb-scroller]" in desk and "top:()=>{ const sc=_scrollerOf(w.card)" in desk
    assert "scroll:(where)=>{ const sc=_scrollerOf(w.card)" in desk
    assert "[data-hb-scroller]" in deck and deck.count("scrollerOf(w)") >= 2
