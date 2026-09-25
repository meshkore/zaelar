"""After a factory reset the agent starts LISTENING: mic open, speaker on (operator, 2026-09-25).

His words: *«cuando después de un reset o una inicialización de cero, el agente empieza arrancado. Es decir, el
orbe escuchando, el micrófono activo, el altavoz activo»*. V2-765 keeps both muted behind the language picker and
undoes that when the engine's `run start` event says the LANGUAGE lifted the gate (`src == "language"`). The
reader looked for `d.extra.src` — but `voice/observer.emit` FLATTENS `extra` into the event, so on the wire it is
`d.src`. The unmute never fired and he had to click the speaker and the mic by hand (session ebbec63e: bot audio
«muted=true volume=0», then `orb:speaker`, `orb:mic` three minutes later). The same nested read hid the Energy
balance from the live battery.

The event here is built by the REAL `observer.emit` (its disk writes swallowed), not typed by hand — a
hand-written event with the nested shape is exactly how the defect passed.
"""
import asyncio
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[4]
FRONT = ROOT / "frontend"

_HTML = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script type="module">
  import * as sse from "/app/services/sse.js?v=2";
  import * as store from "/app/core/store.js?v=2";
  window.__sse = sse; window.__store = store;
  window.__fired = 0;
  document.addEventListener("hb:language-ready", () => { window.__fired += 1; });
  window.__ready = true;
</script></body></html>"""


class _SinkQ:
    def put_nowait(self, item):
        pass


def _wire_event(monkeypatch, kind, label, text, extra):
    """What the SSE stream carries: observer.emit's own event, serialised the way /events does."""
    from voice import observer
    monkeypatch.setattr(observer, "_write_q", _SinkQ())
    ev = observer.emit(kind, label, text=text, extra=extra)
    return json.loads(json.dumps(ev, ensure_ascii=False))


def _serve(route, url):
    path = url.split("?", 1)[0].split("http://zaelar.test", 1)[-1].lstrip("/")
    f = FRONT / path
    if not f.is_file():
        return asyncio.ensure_future(route.fulfill(status=404, body="no"))
    ctype = {"js": "text/javascript", "css": "text/css"}.get(f.suffix.lstrip("."), "text/plain")
    return asyncio.ensure_future(route.fulfill(status=200, content_type=ctype,
                                               body=f.read_text(encoding="utf-8")))


def _route_in_browser(events):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="text/html", body=_HTML)))
            await pg.route("http://zaelar.test/app/**", lambda r: _serve(r, r.request.url))
            await pg.route("http://zaelar.test/api/**", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="application/json", body="{}")))
            await pg.goto("http://zaelar.test/")
            await pg.wait_for_function("() => window.__ready === true")
            out = await pg.evaluate("""(evs) => {
              for (const d of evs) window.__sse.routeEvent({}, d);
              const e = window.__store.energy() || {};
              return { fired: window.__fired, balance: e.balance ?? null };
            }""", events)
            out["errors"] = errors
            await b.close()
            return out
    return asyncio.run(go())


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def test_the_language_lifting_the_gate_unmutes_mic_and_speaker(playwright_available, monkeypatch):
    ev = _wire_event(monkeypatch, "run", "start", "en marcha por language", {"src": "language", "workers": 0})
    assert ev.get("src") == "language" and "extra" not in ev, f"the bus contract is FLAT: {ev}"
    m = _route_in_browser([ev])
    assert not m["errors"], m["errors"]
    assert m["fired"] == 1, "the language lock must bring the mic and speaker back — nobody clicks ⏻ here"


def test_the_operators_own_start_does_not_masquerade_as_the_language(playwright_available, monkeypatch):
    ev = _wire_event(monkeypatch, "run", "start", "en marcha", {"src": "operator"})
    assert _route_in_browser([ev])["fired"] == 0


def test_the_energy_balance_reaches_the_battery(playwright_available, monkeypatch):
    ev = _wire_event(monkeypatch, "energy", "saldo", "", {"balance": 4321, "capacity": 5000})
    assert _route_in_browser([ev])["balance"] == 4321, "the battery must drop live with the pushed balance"
