"""A widget change that lands while its card is still coming up is POSTPONED, never dropped (V2-688).

MEASURED on the operator's own session, 2026-09-14 (`T5·ca89`). He said «Okay, can you open my agenda,
connect to my Google Calendar?» and nothing happened — «no parece darse por aludido ni me muestra el wizard
ni nada». Every single piece did its job, which is why it was invisible:

    t+0 ms   widget/show   agenda        (src flash)   — the canvas starts mounting the card
    t+6 ms   widget/action connect                     — the connect data-op RUNS
    t+8 ms   widget/data   agenda        (src flash)   — the store saved and told the canvas

The action had written the token that steers the card to its connect screen (`gcal.push_connect_screen`,
V2-686) and the store was holding it — verified afterwards in his live widget data: `{"n": 4, ...}`. The
notice reached `refreshData`, which returned on its first line because the card had no `_mod` yet: it was
still mounting. A card that is mounting is precisely a card whose data fetch may already have gone out, so
what the early return threw away was the newer truth.

The window is microseconds wide and ONE natural sentence hits it every time, because «open X and do Y to
it» is two orders in one turn. Same rule as every other queue in this engine — postpone, don't lose.

RENDERED, not read: whether a notice survives a mount is a timing fact about the real `Desktop`, and the
early return it died on looked completely correct in source.
"""
import asyncio
import pathlib
import re

import pytest

DESKTOP = pathlib.Path("frontend/app/widgets/desktop.js")

_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  html,body{margin:0;height:100%}
  #desk{position:fixed;inset:0}
</style></head><body><div id="desk"><div id="wstage"></div></div></body></html>"""

# A Desktop with exactly the collaborators `refreshData` touches, and a FETCH we drive by hand: the point of
# the test is WHEN the data is read, so the reads have to be observable and completable on command.
_SETUP = """(async () => {
  const D = window.__Desktop;
  const d = Object.create(D.prototype);
  d.stage = document.getElementById("wstage");
  d.wins = new Map();
  d._persist = () => {};
  d._applyLiveTitle = () => {};
  window.__fetched = [];
  window.__pending = [];
  window.fetch = (url) => {
    window.__fetched.push(String(url));
    return new Promise(res => window.__pending.push(
      body => res({ json: () => Promise.resolve(body) })));
  };
  // A card the way `show()` leaves it BEFORE the module has rendered: present in `wins`, no `_mod` yet.
  window.__mounting = (id) => {
    const body = document.createElement("div");
    d.stage.appendChild(body);
    d.wins.set(id, { body, card: body });
    return d.wins.get(id);
  };
  // …and what `show()` does at the END of a successful mount, in the same order, including the flush.
  window.__finishMount = (id, data) => {
    const w = d.wins.get(id);
    w._renders = [];
    w._dataSig = JSON.stringify(data);
    w._mod = { render: (el, dd) => w._renders.push(dd) };
    w._ctx = {};
    w._lastData = data;
    if(w._refreshPending){ w._refreshPending = false; d.refreshData(id); }
    return true;
  };
  window.__d = d;
  return true;
})()"""


def _module_source() -> str:
    """desktop.js with its top-of-file imports stubbed — the route-mocked page has no static server, so a
    real `../core` import kills the whole script tag in silence (the V2-613 trap, documented by its
    neighbours here)."""
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
            pg = await b.new_page(viewport={"width": 1200, "height": 800})
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


def test_a_notice_during_a_mount_is_remembered_and_read_when_the_card_is_ready(playwright_available):
    """The operator's incident, step for step: show, then a save 8 ms later, then the mount finishes."""
    out, errors = _run("""(async () => {
      const d = window.__d;
      const w = window.__mounting("agenda");
      await d.refreshData("agenda");                       // the save lands mid-mount
      const duringMount = { fetched: window.__fetched.length, pending: !!w._refreshPending };
      window.__finishMount("agenda", { connect: null });    // the card comes up with the OLD data
      await new Promise(r => setTimeout(r, 0));
      const asked = window.__fetched.length;
      window.__pending.pop()({ connect: { n: 4 } });        // the re-read answers with the token
      await new Promise(r => setTimeout(r, 0));
      return { duringMount, asked, renders: w._renders.map(x => x && x.connect && x.connect.n) };
    })()""")
    assert not errors, errors
    assert out["duringMount"] == {"fetched": 0, "pending": True}, \
        "a card that is still mounting is not fetched from — but the notice has to be REMEMBERED"
    assert out["asked"] == 1, "and re-read exactly once, as soon as the card can take it"
    assert out["renders"] == [4], \
        "the card ends up showing the change it was told about — this is the whole incident"


def test_a_notice_while_a_fetch_is_IN_FLIGHT_is_read_again_afterwards(playwright_available):
    """The same hole, one state later: the in-flight guard coalesced a burst into «whichever fetch is
    already running». But that fetch may have been issued BEFORE the save, so the operator's change can be
    exactly the one it cannot contain."""
    out, errors = _run("""(async () => {
      const d = window.__d;
      const w = window.__mounting("agenda");
      window.__finishMount("agenda", { connect: null });
      const first = d.refreshData("agenda");               // fetch #1, in flight
      await d.refreshData("agenda");                       // the save lands while it is out
      const pending = !!w._refreshPending;
      window.__pending.shift()({ connect: null });          // #1 answers with the STALE payload
      await first;
      await new Promise(r => setTimeout(r, 0));
      const asked = window.__fetched.length;
      if(window.__pending.length) window.__pending.shift()({ connect: { n: 7 } });
      await new Promise(r => setTimeout(r, 0));
      return { pending, asked, renders: w._renders.map(x => x && x.connect && x.connect.n) };
    })()""")
    assert not errors, errors
    assert out["pending"] is True, "the second notice is remembered rather than folded into a stale fetch"
    assert out["asked"] == 2, "so the data is read again once the first answer is in"
    assert out["renders"] == [7], "and the change that arrived last is the one on screen"


def test_the_mount_FLUSHES_what_arrived_while_it_was_running(playwright_available):
    """The other half of the fix lives at the end of `show()`, which this harness cannot run (it fetches a
    manifest and imports a module over the network). So it is measured where it can be: the line exists, it
    is inside `show`, and it comes AFTER the assignment that makes the card refreshable — before it, the
    flush would hit the very early return it exists to undo."""
    src = re.sub(r"//.*", "", DESKTOP.read_text(encoding="utf-8"))     # comment-stripped: prose is not wiring
    # Sliced to the METHOD DEFINITION, not to the first mention: `show`'s own catch calls `_mountError`,
    # so the bare name cuts the slice in half and the guard then measures a fragment.
    show = src[src.index("async show("):src.index("_mountError(w, baseId, msg){")]
    assert "w._mod = mod" in show, "the mount's own marker moved — re-anchor this guard"
    assert "_refreshPending" in show, \
        "a mount that does not flush the notices it swallowed re-opens the operator's incident"
    assert show.index("w._mod = mod") < show.index("_refreshPending"), \
        "the flush has to come AFTER the card is refreshable, or it hits the early return it is undoing"
