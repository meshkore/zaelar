"""The map card, RENDERED in Chromium from the shipped widget.js (demo run, 2026-09-26): every pin lands INSIDE
the view (the fit is real), the pins are numbered in order, the list says the same, the selected one is marked,
a pin click goes through ctx.action("select"), the tiles are requested for the fitted zoom, and a hostile place
name is text."""
import asyncio
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
WJS = (ROOT / "widgets/map/widget.js").read_text(encoding="utf-8")
DATA = {"title": "This weekend", "selected": 2, "places": [
    {"name": "Griffith Observatory", "address": "Los Angeles", "lat": 34.118, "lon": -118.300},
    {"name": "Crypto.com Arena <img src=x>", "address": "Los Angeles", "lat": 34.043, "lon": -118.267},
    {"name": "Runyon Canyon", "address": "Los Angeles", "lat": 34.112, "lon": -118.350}]}

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#1F242B}
#card{width:640px;height:520px}</style></head><body><div id="card"></div>
<script type="module">
  import { render } from "/w.js";
  window.__acts = [];
  render(document.getElementById("card"), __DATA__, { action: (a, p) => window.__acts.push([a, p]), lang: "en" });
  window.__ready = true;
</script></body></html>"""


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_the_pins_fit_the_view_and_select_through_the_voice_door(playwright_available):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 900, "height": 700})
            tiles, errors = [], []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("https://*.basemaps.cartocdn.com/**", lambda r: (tiles.append(r.request.url),
                           asyncio.ensure_future(r.fulfill(status=200, content_type="image/png", body=b""))))
            await pg.route("http://map.test/", lambda r: asyncio.ensure_future(r.fulfill(
                status=200, content_type="text/html", body=_HTML.replace("__DATA__", json.dumps(DATA)))))
            await pg.route("http://map.test/w.js", lambda r: asyncio.ensure_future(r.fulfill(
                status=200, content_type="text/javascript", body=WJS)))
            await pg.goto("http://map.test/")
            await pg.wait_for_function("() => window.__ready === true")
            await pg.wait_for_timeout(300)
            m = await pg.evaluate("""() => {
              const v = document.querySelector('.mapview').getBoundingClientRect();
              const pins = [...document.querySelectorAll('.mappin')];
              return {
                inside: pins.every(p => { const r = p.getBoundingClientRect();
                  const x = r.left + r.width / 2, y = r.bottom;
                  return x > v.left && x < v.right && y > v.top && y < v.bottom; }),
                nums: pins.map(p => p.querySelector('b').textContent),
                on: pins.filter(p => p.classList.contains('is-on')).map(p => p.querySelector('b').textContent),
                rows: [...document.querySelectorAll('.maprow span')].map(s => s.textContent),
                injected: !!document.querySelector('.maprow img, .mappin img'),
                tiles: document.querySelectorAll('.maptile').length,
              };
            }""")
            await pg.click('.mappin:nth-of-type(1)')
            m["acts"] = await pg.evaluate("() => window.__acts")
            m["tile_urls"], m["errors"] = tiles, errors
            await b.close()
            return m
    m = asyncio.run(go())
    assert not m["errors"], m["errors"]
    assert m["inside"], "every pin must land inside the fitted view"
    assert m["nums"] == ["1", "2", "3"] and m["on"] == ["2"], m
    assert m["rows"][0] == "Griffith Observatory" and "<img" in m["rows"][1] and not m["injected"]
    assert m["tiles"] >= 4 and m["tile_urls"], "the fitted view is covered by tiles"
    z = {int(u.split("/voyager/")[1].split("/")[0]) for u in m["tile_urls"]}
    assert len(z) == 1 and 11 <= z.pop() <= 15, "three places across LA fit at city zoom"
    assert m["acts"] and m["acts"][0][0] == "select"
