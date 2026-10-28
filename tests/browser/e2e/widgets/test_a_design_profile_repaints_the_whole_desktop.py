"""A design profile repaints the WHOLE desktop, instantly and durably (V2-617).

The pinned hexes moved in V2-691 (the legibility pass lifted the ladder off near-black and
lightened the accent); what is asserted is unchanged — a consumer of a token has to resolve to
the PROFILE's own value, which is what catches an override key that silently overrides nothing.

The operator's requirement, verbatim in spirit: «tiene que ser un sistema integral de plantillas aplicado a
todo» — profiles selectable in ⚙, everything customizable (accent, type size, typeface), nothing
half-skinned. The mechanism that makes that TRUE rather than aspirational is that the entire desktop and
every widget read one token contract (core/palette.css), and a profile is a token override map
(core/themes.js) that services/theme.js writes as inline custom properties on <html> — inline beats the
stylesheet, so one swap reaches every reader at once.

RENDERED with the REAL modules — palette.css, themes.js, theme.js, store.js, reactive.js, api.js — served
from disk into a real page. A probe element styled `background:var(--hb-bg)` is the «whole desktop» stand-in:
asserting the resolved COLOR of a token consumer, not the inline property, is what catches a profile map
whose keys don't match the stylesheet's tokens (they would silently override nothing).

Persistence is asserted on both layers: localStorage (instant paint on the next load) and /api/settings
(the ACCOUNT's copy — a cloud Machine's browser cache is not where a preference should live), including the
boot reconcile where the server's choice wins over a stale local one.
"""
import asyncio
import json
import pathlib

import pytest

APP = pathlib.Path("frontend/app")

_HTML = """<!doctype html><html><head><meta charset="utf-8">
<meta name="theme-color" id="themeColorMeta" content="">
<link rel="stylesheet" href="/app/core/palette.css">
<link rel="stylesheet" href="/app/styles.css">
<style>#probe{background:var(--hb-bg);color:var(--hb-accent);font-size:1rem;width:13rem}</style>
</head><body><div id="probe">probe</div></body></html>"""
# NOTE the REAL app stylesheet is linked: the size test measures styles.css's own
# `html{font-size:var(--hb-fs-base)}` wiring, not a fixture copy of it — a fixture that hand-writes the rule
# under test measures a different product (the V2-608 lesson).

_BOOT = """
import { initTheme, setThemeProfile, setThemeCustom, themeProfile, themeCustom } from "/app/services/theme.js?v=2";
import { setTheme, theme } from "/app/core/store.js?v=2";
window.__t = { initTheme, setThemeProfile, setThemeCustom, themeProfile, themeCustom, setTheme, theme };
initTheme();
window.__ready = true;
"""

_READ = """() => {
  const cs = getComputedStyle(document.documentElement);
  const probe = getComputedStyle(document.getElementById("probe"));
  return {
    canvas: cs.getPropertyValue("--canvas").trim(),
    accent: cs.getPropertyValue("--hb-accent").trim(),
    probeBg: probe.backgroundColor,
    probeColor: probe.color,
    probeWidth: Math.round(parseFloat(probe.width)),
    rootFs: getComputedStyle(document.documentElement).fontSize,
    profile: window.__t.themeProfile(),
    lsProfile: localStorage.getItem("hb_theme_profile"),
    lsCustom: localStorage.getItem("hb_theme_custom"),
    metaColor: document.getElementById("themeColorMeta").content,
  };
}"""


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _serve(route):
    """Serve the REAL frontend/app tree; /api/settings answers from the mutable `server` dict."""
    url = route.request.url
    path = url.split("zaelar.test")[1].split("?")[0]
    if path == "/":
        return route.fulfill(status=200, content_type="text/html", body=_HTML)
    if path.startswith("/app/"):
        f = APP / path[len("/app/"):]
        if f.exists():
            ct = "text/css" if f.suffix == ".css" else "application/javascript"
            return route.fulfill(status=200, content_type=ct, body=f.read_text(encoding="utf-8"))
    return route.fulfill(status=404, body="")


async def _boot(pw, server_theme=None, posts=None):
    b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
    pg = await b.new_page(viewport={"width": 1200, "height": 800})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    async def api_route(route):
        if route.request.method == "POST":
            if posts is not None:
                try:
                    posts.append(json.loads(route.request.post_data or "{}"))
                except Exception:
                    posts.append({})
            return await route.fulfill(status=200, content_type="application/json",
                                       body=json.dumps({"ok": True, "applied": [], "needs_reconnect": False}))
        return await route.fulfill(status=200, content_type="application/json",
                                   body=json.dumps({"knobs": [], "theme": server_theme or {}}))

    # Playwright consults routes LAST-registered-first: the catch-all goes in FIRST so the /api/settings
    # handler (registered after) wins for its own URL instead of falling into the file server's 404.
    await pg.route("http://zaelar.test/**", lambda r: _serve(r))
    await pg.route("http://zaelar.test/api/settings", api_route)
    await pg.goto("http://zaelar.test/")
    await pg.add_script_tag(content=_BOOT, type="module")
    await pg.wait_for_function("() => !!window.__ready")
    await pg.wait_for_timeout(60)   # let the settings reconcile land
    return b, pg, errors


def _rgb(hexs):
    hexs = hexs.lstrip("#")
    return f"rgb({int(hexs[0:2], 16)}, {int(hexs[2:4], 16)}, {int(hexs[4:6], 16)})"


def test_the_default_skin_is_grafito_and_a_token_consumer_wears_it(playwright_available):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            m = await pg.evaluate(_READ)
            await b.close()
            return m, errors
    m, errors = asyncio.run(go())
    assert m["canvas"] == "#16191E", f"default canvas must be grafito: {m}"
    assert m["probeBg"] == _rgb("1F242B"), f"a var(--hb-bg) consumer must wear the card surface: {m}"
    assert m["probeColor"] == _rgb("AE90FF"), f"the accent is the heliotrope: {m}"
    assert not errors, errors


def test_switching_to_clasico_repaints_a_real_consumer(playwright_available):
    """The old navy stays available whole — and the assertion is the probe's RESOLVED color, which fails if
    a profile key ever drifts from the stylesheet's token names."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            await pg.evaluate("() => window.__t.setThemeProfile('clasico')")
            m = await pg.evaluate(_READ)
            await pg.evaluate("() => window.__t.setThemeProfile('grafito')")
            back = await pg.evaluate(_READ)
            await b.close()
            return m, back, errors
    m, back, errors = asyncio.run(go())
    assert m["probeBg"] == _rgb("141d29"), f"clasico's card surface: {m}"
    assert m["canvas"] == "#0a0f16" and m["profile"] == "clasico" and m["lsProfile"] == "clasico", m
    assert m["metaColor"] == "#0a0f16", f"the browser-chrome color must follow the profile: {m}"
    # and BACK: grafito is «no overrides», so the swap must REMOVE clasico's inline vars — a profile that
    # bleeds into the next one is exactly the half-skinned desktop the operator forbade
    assert back["canvas"] == "#16191E" and back["probeBg"] == _rgb("1F242B"), f"clasico bled into grafito: {back}"


def test_a_custom_accent_beats_the_profile_and_clearing_restores_it(playwright_available):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            await pg.evaluate("() => window.__t.setThemeCustom({accent:'#22AA66'})")
            custom = await pg.evaluate(_READ)
            await pg.evaluate("() => window.__t.setThemeProfile('ambar')")
            still = await pg.evaluate(_READ)
            await pg.evaluate("() => window.__t.setThemeCustom({accent:''})")
            cleared = await pg.evaluate(_READ)
            await b.close()
            return custom, still, cleared
    custom, still, cleared = asyncio.run(go())
    assert custom["probeColor"] == _rgb("22AA66"), f"custom accent must reach a consumer: {custom}"
    assert still["probeColor"] == _rgb("22AA66"), f"a custom accent survives a profile swap: {still}"
    assert cleared["probeColor"] == _rgb("F2CE6B"), f"clearing returns the PROFILE's accent (ámbar): {cleared}"


def test_the_size_knob_scales_the_desktop_through_the_root(playwright_available):
    """`html{font-size:var(--hb-fs-base)}` + rem authoring = one token scales everything. The probe is
    rem-sized in BOTH axes that matter (type and width), so this fails if the root wiring is dropped."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            before = await pg.evaluate(_READ)
            await pg.evaluate("() => window.__t.setThemeCustom({fs:'l'})")
            after = await pg.evaluate(_READ)
            await b.close()
            return before, after
    before, after = asyncio.run(go())
    assert before["rootFs"] == "17px", f"grafito's default base is 17px: {before}"
    assert after["rootFs"] == "18.5px", f"the L step: {after}"
    assert after["probeWidth"] > before["probeWidth"], "a rem-sized element must grow with the knob"


def test_the_choice_survives_a_reload_and_the_server_copy_wins(playwright_available):
    """Layer 1: localStorage paints the saved profile on the next load with no server. Layer 2: the account's
    copy (settings.json via /api/settings) OVERRIDES a stale local one — a fresh browser has no localStorage,
    the account still has its skin."""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            # save clasico, reload the same origin → localStorage repaints it
            b, pg, errors = await _boot(pw)
            await pg.evaluate("() => window.__t.setThemeProfile('clasico')")
            await pg.goto("http://zaelar.test/")
            await pg.add_script_tag(content=_BOOT, type="module")
            await pg.wait_for_function("() => !!window.__ready")
            local = await pg.evaluate(_READ)
            await b.close()
            # a server that says ambar beats a localStorage that says clasico
            b2, pg2, _ = await _boot(pw, server_theme={"profile": "ambar", "custom": {}})
            server = await pg2.evaluate(_READ)
            await b2.close()
            return local, server
    local, server = asyncio.run(go())
    assert local["profile"] == "clasico" and local["probeBg"] == _rgb("141d29"), f"localStorage layer: {local}"
    assert server["profile"] == "ambar" and server["probeColor"] == _rgb("F2CE6B"), f"server layer: {server}"
    assert server["lsProfile"] == "ambar", "the reconcile must refresh the local mirror too"


def test_a_change_is_saved_to_the_account(playwright_available):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            posts = []
            b, pg, errors = await _boot(pw, posts=posts)
            await pg.evaluate("() => window.__t.setThemeProfile('ambar')")
            await pg.evaluate("() => window.__t.setThemeCustom({fs:'s'})")
            await pg.wait_for_timeout(80)
            await b.close()
            return posts
    posts = asyncio.run(go())
    assert any(p.get("theme_profile") == "ambar" for p in posts), f"profile must reach /api/settings: {posts}"
    assert any((p.get("theme_custom") or {}).get("fs") == "s" for p in posts), f"custom too: {posts}"


def test_light_mode_gets_the_grafito_paper_not_an_inverted_navy(playwright_available):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b, pg, errors = await _boot(pw)
            await pg.evaluate("() => window.__t.setTheme('light')")
            m = await pg.evaluate(_READ)
            await b.close()
            return m
    m = asyncio.run(go())
    assert m["canvas"] == "#F4F5F7", f"light grafito is cool paper, never pure white: {m}"
    assert m["probeColor"] == _rgb("6D4AE8"), f"the accent gains pigment on paper for contrast: {m}"


_PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api
app = FastAPI(); app.include_router(pages.router); app.include_router(i18n_api.router)
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

_PANE = """async () => {
  const side = document.querySelector('.cf-nav.cf-side');
  const entry = side && side.querySelector('.cf-nav-top[data-tab="apariencia"]');
  const vis = el => { if (!el) return false; const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0 && getComputedStyle(el).display !== 'none'; };
  const themes = Object.keys((await import('/static/app/core/themes.js?v=1')).THEMES);
  const cards = [...document.querySelectorAll('.cf-th-card')];
  return {
    menu: !!side, entry: vis(entry), label: entry ? entry.textContent.trim() : '',
    entryOn: !!(entry && entry.classList.contains('on')),
    themes, cards: cards.map(c => c.dataset.profile), on: cards.filter(c => c.classList.contains('on')).map(c => c.dataset.profile),
    lsProfile: localStorage.getItem('hb_theme_profile'),
  };
}"""


@pytest.fixture(scope="module")
def config_pane(playwright_available):
    """The ⚙ panel RENDERED on the real frontend (its own preview server, never the operator's engine): the
    «Apariencia» entry of the left menu, its profile catalog, and one profile chosen by a click."""
    import os
    import socket
    import subprocess
    import sys
    from playwright.sync_api import sync_playwright
    from tests.waiting import port_listening
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    engine = os.path.abspath(".")
    proc = subprocess.Popen([sys.executable, "-c", _PREVIEW % (engine, os.path.join(engine, "frontend"), port)],
                            cwd=engine, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        # Against a CLOCK, and a server that never comes up FAILS naming the port — a skip would hide it.
        port_listening(port, timeout_s=30.0)
        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True, args=["--no-sandbox"])
            ctx = b.new_context(viewport={"width": 1280, "height": 800})
            # This tab already had its first run (`core/first-run.js` wipes and reloads once per tab otherwise).
            ctx.add_init_script("try { sessionStorage.setItem('hb_first_run_takeover', '1'); } catch (_) {}")
            pg = ctx.new_page()
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.goto(f"http://127.0.0.1:{port}/", wait_until="domcontentloaded")
            pg.wait_for_timeout(2200)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil').forEach(e => e.remove())")
            pg.click("#cfgBtn")
            pg.wait_for_timeout(700)
            entry = pg.locator('.cf-side .cf-nav-top[data-tab="apariencia"]')
            if entry.count():                       # absent → the assertions below say so, not a click timeout
                entry.first.click()
                pg.wait_for_timeout(400)
            out = {"opened": pg.evaluate(_PANE), "picked": None}
            pick = next((p for p in out["opened"]["cards"] if p not in out["opened"]["on"]), None)
            if pick:
                pg.click(f'.cf-th-card[data-profile="{pick}"]')
                pg.wait_for_timeout(400)
            out["picked"], out["chosen"], out["errors"] = pick, pg.evaluate(_PANE), errors
            b.close()
        return out
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover
            proc.kill()


def test_the_config_panel_offers_the_system(config_pane):
    """The ⚙ seam, rendered: «Apariencia» is an entry of the panel's ONE left menu (since 2026-10-26 the top tabs
    are gone), its pane paints the whole profile catalog, and a click on a profile goes through the theme service
    — the one that persists it — so the choice is the panel's state AND the browser's."""
    o = config_pane["opened"]
    assert o["menu"] and o["entry"], f"the left menu must carry a visible «Apariencia» entry: {o}"
    labels = {json.loads(pathlib.Path(f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
              .get("config.tab.apariencia") for lang in ("es", "en")}
    assert o["label"] in labels, f"the entry must read the bundle's label, got {o['label']!r} (bundles: {labels})"
    assert o["entryOn"], "the entry clicked must be the one marked as the open area"
    assert sorted(o["cards"]) == sorted(o["themes"]), f"the pane must paint every profile: {o['cards']} vs {o['themes']}"
    c = config_pane["chosen"]
    assert c["on"] == [config_pane["picked"]], f"the clicked profile must become the chosen one: {c['on']}"
    assert c["lsProfile"] == config_pane["picked"], f"the theme service must persist it: {c['lsProfile']}"
    assert config_pane["errors"] == [], config_pane["errors"]
    for lang in ("es", "en"):
        bundle = json.loads(pathlib.Path(f"i18n/genesis/{lang}/ui.json").read_text(encoding="utf-8"))
        assert bundle.get("config.tab.apariencia"), f"{lang}: the tab label must exist"
        assert bundle.get("config.theme.title"), f"{lang}: the pane strings must exist"
