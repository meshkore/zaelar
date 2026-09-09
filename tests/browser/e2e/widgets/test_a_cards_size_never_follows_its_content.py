"""A card's size belongs to the OPERATOR, never to its content (V2-630).

MEASURED, operator's screenshots 2026-09-09 (session 7be94951): the musica card grew and shrank on every song
change — «Louis Armstrong - What A Wonderful World (Official Video)» rendered a visibly wider card than
«Imagine - John Lennon…», with nobody resizing anything. His rule, verbatim in spirit: *«el tamaño de los
widgets debe ser fijo — si el texto cabe bien y si no cabe, se acorta; el usuario decidirá si lo hace más
grande o más pequeño»*. The mechanism: `.hb-win` has no width of its own (shrink-to-fit), musica declares no
manifest size, and the playback bar's `white-space:nowrap` title propagates its max-content width straight up
into the card.

The fix is CLASS-level, in the canvas: after a card's first real render, `_freezeSize` writes any still-auto
dimension as explicit px — from then on, content changes truncate or scroll INSIDE the card. Only the
operator's gestures (resize handles, maximize, voice resize, arrange) and the canvas itself (_fit on shrink)
touch a card's size afterwards.

RENDERED, not read: whether a longer title grows the card is a layout fact no source test can see.
"""
import asyncio
import json
import pathlib
import re

import pytest

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  :root{ --chatdock-l:0px; --chatdock-r:0px; }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#0a1017}
  #desk{position:fixed;top:0;bottom:0;left:var(--chatdock-l);right:var(--chatdock-r);transform:translate3d(0,0,0)}
  /* The load-bearing lines of the REAL .hb-win rule (desktop.js): position:absolute + NO width = shrink-to-fit,
     which is exactly the auto-sizing under test. Padding kept so the px the freeze writes are border-box-real. */
  .hb-win{position:absolute;padding:30px 16px 16px;max-width:92vw;max-height:82vh;overflow:hidden;
          display:flex;flex-direction:column;background:#223}
  .bart{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font:13px sans-serif;color:#fff}
</style></head><body>
  <div id="desk"><div id="wstage"></div></div><div id="activity"></div>
</body></html>"""

_SETUP = """(async () => {
  const D = window.__Desktop;
  const d = Object.create(D.prototype);
  d.stage = document.getElementById("wstage");
  d.wins = new Map();
  d.tile = {w:400, h:340, top:70, pad:14};
  d.grid = 5;
  d._meta = {musica:{}, navegador:{min:{w:520, h:300}}};
  d._persist = () => {};
  d._uiAudit = () => {};
  d.z = 20;
  // A card the way show() builds one BEFORE any explicit size is applied: absolute, no width/height,
  // content inside. The .bart line is the playback-bar title — the nowrap driver of the real incident.
  window.__mk = (id, title) => {
    const c = document.createElement("div");
    c.className = "hb-win"; c.dataset.wid = id;
    c.style.left = "80px"; c.style.top = "100px";
    const t = document.createElement("div");
    t.className = "bart"; t.textContent = title;
    c.appendChild(t);
    d.stage.appendChild(c);
    d.wins.set(id, {card:c, title:t});
    return c;
  };
  window.__d = d;
  return true;
})()"""


def _module_source() -> str:
    """desktop.js with its top-of-file imports stubbed — same shape and same warning as the refit suite: this
    route-mocked page has no static server, so a real ../core import fails the whole script tag in silence."""
    src = DESKTOP.read_text(encoding="utf-8")
    src = re.sub(r'^import \{ t as tr \}.*$', 'const tr = (k) => k;', src, count=1, flags=re.M)
    src = re.sub(r'^import \* as store from .*$', 'const store = { lang: () => "en" };', src, count=1, flags=re.M)
    leftover = re.findall(r'^import .*$', src, flags=re.M)
    assert not leftover, f"_module_source() does not stub: {leftover} — every import needs a stub line above"
    return src + "\nwindow.__Desktop = Desktop;\n"


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright.async_api  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


def _run(script):
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            b = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            pg = await b.new_page(viewport={"width": 1400, "height": 900})
            errors = []
            pg.on("pageerror", lambda e: errors.append(str(e)))
            await pg.route("http://zaelar.test/", lambda r: asyncio.ensure_future(
                r.fulfill(status=200, content_type="text/html", body=_HTML)))
            await pg.goto("http://zaelar.test/")
            await pg.add_script_tag(content=_module_source(), type="module")
            await pg.wait_for_function("() => !!window.__Desktop")
            await pg.evaluate(_SETUP)
            out = await pg.evaluate(script)
            await b.close()
            return out, errors
    return asyncio.run(go())


SHORT = "Imagine"
LONG = "Louis Armstrong - What A Wonderful World (Official Video) [Remastered 4K] - Topic"


def test_an_auto_sized_card_would_grow_with_its_title_without_the_freeze(playwright_available):
    """The CONTROL: proves the harness can see the defect at all. An unfrozen shrink-to-fit card with a nowrap
    title genuinely widens when the title lengthens — if this stops being true, the other tests measure air."""
    out, errors = _run(f"""async () => {{
      const c = window.__mk("musica", "{SHORT}");
      const w0 = c.getBoundingClientRect().width;
      c.querySelector(".bart").textContent = "{LONG}";
      const w1 = c.getBoundingClientRect().width;
      return {{w0, w1}};
    }}""")
    assert not errors, errors
    assert out["w1"] > out["w0"] + 50, f"the harness cannot reproduce the growth: {out}"


def test_a_longer_song_title_no_longer_resizes_a_frozen_card(playwright_available):
    """The incident itself: after the first-render freeze, a song change cannot move the card's width."""
    out, errors = _run(f"""async () => {{
      const c = window.__mk("musica", "{SHORT}");
      window.__d._freezeSize(c, "musica");
      const w0 = c.getBoundingClientRect().width;
      c.querySelector(".bart").textContent = "{LONG}";
      const w1 = c.getBoundingClientRect().width;
      return {{w0, w1, styleW: c.style.width, styleH: c.style.height, maxW: c.style.maxWidth}};
    }}""")
    assert not errors, errors
    assert out["w1"] == out["w0"], f"the frozen card still tracked its title: {out}"
    assert out["styleW"].endswith("px") and out["styleH"].endswith("px")
    assert out["maxW"] == "none"


def test_dimensions_the_operator_already_set_are_his(playwright_available):
    """A card restored with saved geometry (or resized by hand) is left byte-for-byte alone."""
    out, errors = _run("""async () => {
      const c = window.__mk("musica", "x");
      c.style.width = "531px"; c.style.height = "377px";
      window.__d._freezeSize(c, "musica");
      return {w: c.style.width, h: c.style.height};
    }""")
    assert not errors, errors
    assert out == {"w": "531px", "h": "377px"}


def test_the_freeze_respects_the_widgets_declared_minimum(playwright_available):
    """A near-empty card cannot freeze below the widget's own floor (`manifest.min`, V2-608's rule) — a card
    frozen into a sliver would be a second bug wearing the fix's name."""
    out, errors = _run("""async () => {
      const c = window.__mk("navegador", "x");           // meta declares min 520x300
      window.__d._freezeSize(c, "navegador");
      return {w: parseInt(c.style.width), h: parseInt(c.style.height)};
    }""")
    assert not errors, errors
    assert out["w"] >= 520 and out["h"] >= 300, out


def test_a_minimized_card_is_never_frozen_at_its_collapsed_bar(playwright_available):
    out, errors = _run("""async () => {
      const c = window.__mk("musica", "x");
      c.classList.add("hb-minned");
      window.__d._freezeSize(c, "musica");
      return {w: c.style.width, h: c.style.height};
    }""")
    assert not errors, errors
    assert out == {"w": "", "h": ""}


def test_show_wires_the_freeze_after_the_preferred_size():
    """Structural, comment-stripped (the V2-573 lesson): the mount path must call _freezeSize on a fresh card,
    AFTER _applyPreferred — the manifest's preferred size fills first, the freeze only pins what is left auto."""
    src = re.sub(r"//[^\n]*", "", DESKTOP.read_text(encoding="utf-8"))
    m_pref = src.find("this._applyPreferred(w.card")
    m_frz = src.find("this._freezeSize(w.card")
    assert m_pref != -1 and m_frz != -1, "show() lost the preferred-size or freeze call"
    assert m_frz > m_pref, "the freeze must run AFTER the preferred size is applied"


def test_musica_declares_a_deterministic_default_width():
    """Without a manifest size the card's FIRST footprint is whatever the current bar title measured — stable
    afterwards (the freeze), but arbitrary per mount. 468 is the pre-V2-615 design width."""
    m = json.loads(pathlib.Path("widgets/musica/manifest.json").read_text(encoding="utf-8"))
    assert isinstance(m.get("size", {}).get("w"), int) and m["size"]["w"] >= 400
