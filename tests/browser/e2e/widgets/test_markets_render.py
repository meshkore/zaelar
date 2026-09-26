"""The markets card, RENDERED in Chromium from the shipped widget.js (demo run, 2026-09-26).

What no source read can say: the line actually has a path with ink, exactly one period tab wears the selected
state, the move is said by an arrow and a number (not by colour alone), the price is formatted, a click on a tab
goes through ctx.action("range"), and a hostile name from the price source is text, never an element.
"""
import asyncio
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
WJS = (ROOT / "widgets/markets/widget.js").read_text(encoding="utf-8")

DATA = {"symbol": "AAPL", "name": "Apple <img src=x onerror=alert(1)>", "currency": "USD", "exchange": "NasdaqGS",
        "range": "1mo", "price": 341.07, "change": 27.6, "change_pct": 8.81, "as_of": 1790366400,
        "points": [[1787700000 + i * 86400, 313 + i * 1.3] for i in range(22)], "ranges": ["1d", "5d", "1mo", "6mo", "1y", "5y"],
        "error": ""}

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#1F242B}
#card{width:560px;height:430px}</style></head><body><div id="card"></div>
<script type="module">
  import { render } from "/w.js";
  window.__acts = [];
  const ctx = { action: (a, p) => window.__acts.push([a, p]), lang: "en", running: true };
  render(document.getElementById("card"), __DATA__, ctx);
  window.__ready = true;
</script></body></html>"""


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _run(data):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 900, "height": 700})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://markets.test/", lambda r: asyncio.ensure_future(r.fulfill(
                status=200, content_type="text/html", body=_HTML.replace("__DATA__", json.dumps(data)))))
            await pg.route("http://markets.test/w.js", lambda r: asyncio.ensure_future(r.fulfill(
                status=200, content_type="text/javascript", body=WJS)))
            await pg.goto("http://markets.test/")
            await pg.wait_for_function("() => window.__ready === true")
            out = await pg.evaluate("""() => {
              const p = document.querySelector('.mktchart svg path[stroke]');
              const box = p ? p.getBoundingClientRect() : null;
              return {
                pathInk: !!p && (p.getAttribute('d') || '').length > 50 && box.width > 200 && box.height > 20,
                tabs: [...document.querySelectorAll('.mkttab')].map(t => t.textContent),
                on: [...document.querySelectorAll('.mkttab.is-on')].map(t => t.textContent),
                chg: (document.querySelector('.mktchg') || {}).textContent || '',
                price: (document.querySelector('.mktprice') || {}).textContent || '',
                name: (document.querySelector('.mktname') || {}).textContent || '',
                injected: !!document.querySelector('.mktname img, img[src=x]'),
                empty: (document.querySelector('.mktempty') || {}).textContent || '',
              };
            }""")
            if data.get("symbol"):
                await pg.click('.mkttab:has-text("1Y")')
                out["acts"] = await pg.evaluate("() => window.__acts")
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


def test_the_chart_paints_and_says_the_move_without_colour_alone(playwright_available):
    m = _run(DATA)
    assert not m["errors"], m["errors"]
    assert m["pathInk"], "the price line must actually paint"
    assert m["tabs"] == ["1D", "5D", "1M", "6M", "1Y", "5Y"] and m["on"] == ["1M"], m
    assert m["chg"].startswith("▲") and "8.81%" in m["chg"], m["chg"]
    assert m["price"] == "341.07"
    assert m["acts"] == [["range", {"range": "1y"}]], "a tab is the same door as the voice"


def test_a_hostile_name_is_text(playwright_available):
    m = _run(DATA)
    assert not m["injected"] and "<img" in m["name"]


def test_an_empty_card_says_how_to_fill_it(playwright_available):
    m = _run({"symbol": ""})
    assert "Apple" in m["empty"] and not m["errors"]
