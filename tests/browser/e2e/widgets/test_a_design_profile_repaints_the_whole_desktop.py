"""A design profile repaints the WHOLE desktop, instantly and durably (V2-617).

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
    assert m["canvas"] == "#0B0B0E", f"default canvas must be grafito: {m}"
    assert m["probeBg"] == _rgb("18181D"), f"a var(--hb-bg) consumer must wear the card surface: {m}"
    assert m["probeColor"] == _rgb("A48FFF"), f"the accent is the heliotrope: {m}"
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
    assert back["canvas"] == "#0B0B0E" and back["probeBg"] == _rgb("18181D"), f"clasico bled into grafito: {back}"


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
    assert cleared["probeColor"] == _rgb("E8A33D"), f"clearing returns the PROFILE's accent (ámbar): {cleared}"


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
    assert server["profile"] == "ambar" and server["probeColor"] == _rgb("E8A33D"), f"server layer: {server}"
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
    assert m["canvas"] == "#F6F5F2", f"light grafito is warm paper: {m}"
    assert m["probeColor"] == _rgb("7A5FF0"), f"the accent gains pigment on paper for contrast: {m}"


def test_the_config_panel_offers_the_system():
    """Source contract for the ⚙ seam: the Apariencia tab exists, renders the profile catalog, and every
    control routes through the theme service (which is what persists to the account)."""
    src = (APP / "components/ConfigPanel.js").read_text(encoding="utf-8")
    assert '{ id: "apariencia" }' in src, "the tab must be declared"
    assert "sec_apariencia" in src and "THEMES" in src, "the pane renders the catalog"
    for call in ("setThemeProfile", "setThemeCustom"):
        assert f"themeSvc.{call}" in src, f"controls must go through the theme service: {call}"
    for lang in ("es", "en"):
        bundle = json.loads(pathlib.Path(f"i18n/bundles/{lang}.json").read_text(encoding="utf-8"))
        assert bundle.get("config.tab.apariencia"), f"{lang}: the tab label must exist"
        assert bundle.get("config.theme.title"), f"{lang}: the pane strings must exist"
