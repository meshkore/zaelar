"""V2-615 — every system widget actually USES the width of the card it is given.

The operator, looking at the mensajería widget's email detail (a Plaid email with several long tracking URLs
wrapping across 4-5 lines each): *"asegúrate que los widgets son auto-resizable... si lo amplío para poder ver
el texto de forma horizontal mejor, que se pueda ampliar. Para este y TODOS los widgets deben ser
auto-escalables."* — dragging a card WIDER must let the content inside actually use that extra width.

Root cause, measured before touching anything: nine of the fourteen system widgets hardcoded their ROOT
element's CSS to `width:min(<N>px,<M>vw)` — a desktop-era idiom AGENTS.md itself already calls out and
half-retracted for the phone shell (V2-574), but never actually fixed on desktop. `frontend/app/widgets/
desktop.js` mounts a widget directly into its card's scroller with NO intermediate fixed-size wrapper (the
card `.hb-win`/`.hb-scroll` are fully fluid, and drag-resize sets `.hb-win`'s width directly) — so the card
genuinely does grow when the operator drags it, and the CAP was 100% the widget's own CSS refusing to use the
space it was handed. `results`, `documento` and `youtube` (V2-597, the same fix built once already) were
already fluid; this closes the gap for the rest of the catalog.

This is a WIDTH-only measurement, deliberately content-independent: `el.className` (the class the root CSS
rule targets) is set unconditionally at the top of every widget's `render()`, before any data-dependent branch
— so even a widget's EMPTY state renders a root whose CSS width rule is in effect, and the test needs no
elaborate filled fixture to be meaningful (unlike an overflow/escapee check, which needs real content to have
anything to overflow).
"""
from __future__ import annotations

import os
import sys

import pytest

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, ENGINE)

# WIDGET catalog + real view_data() reused from the phone-render harness rather than re-invented — the same
# discovery the operator already trusts to measure "every system widget", one CARD size apart.
from tests.browser.e2e.mobile.render_widgets_on_a_phone import widget_ids, widget_data  # noqa: E402

CARD_WIDTH = 900   # well past every old cap in the catalog (440-920px) — a card the operator deliberately widened
MIN_FRACTION = 0.9  # the root must track the card, not merely be "somewhat wider than before"

PAGE = f"""<!doctype html><meta charset="utf-8">
<style>html,body{{margin:0;padding:0;background:#0a1017;color:#e8eef6}}
#card{{width:{CARD_WIDTH}px}}</style>
<div id="card"><div id="host"></div></div>
"""
# `#host` (the mount point `render(el, ...)` receives) is DELIBERATELY given no width of its own — an ID
# selector on it would out-specificity ANY class rule the widget declares, so a capped `width:min(480px,92vw)`
# would be silently overridden to 900px by the harness itself and the test could never fail. `#card` carries
# the card size instead; `#host`'s rendered width is governed ENTIRELY by the widget's own CSS, exactly as it
# would be inside the real desktop canvas's fluid `.hb-win`/`.hb-scroll`.


@pytest.fixture(scope="module")
def playwright_available():
    try:
        import playwright  # noqa: F401
    except Exception:  # pragma: no cover
        pytest.skip("playwright not installed")
    return True


@pytest.fixture(scope="module")
def widths(playwright_available):
    """{widget_id: rendered root width in px}, measured once for the whole module (one browser, one pass)."""
    from playwright.sync_api import sync_playwright

    ids = widget_ids()
    data_by_id = {wid: widget_data(wid) for wid in ids}
    out: dict[str, dict] = {}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": CARD_WIDTH + 40, "height": 900})

        def route(r):
            path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
            if path in ("page", ""):
                return r.fulfill(status=200, body=PAGE, headers={"content-type": "text/html; charset=utf-8"})
            if path.startswith("widgets/"):
                fp = os.path.join(ENGINE, path)
            else:
                return r.fulfill(status=404, body="")
            if not os.path.isfile(fp):
                return r.fulfill(status=404, body="")
            with open(fp, "rb") as fh:
                r.fulfill(status=200, body=fh.read(), headers={"content-type": "application/javascript"})

        page = ctx.new_page()
        page.route("**/*", route)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        for wid in ids:
            del errors[:]
            page.goto("http://widgets.test/page", wait_until="load")
            res = page.evaluate(
                """async ([wid, data]) => {
                     const host = document.getElementById('host');
                     const ctx = { action: async () => ({}), close: () => {}, top: () => {}, running: true };
                     try {
                       const mod = await import(`/widgets/${wid}/widget.js`);
                       await mod.render(host, data, ctx);
                     } catch (e) { return { threw: String(e && e.message || e) }; }
                     // `render(el, ...)` mounts INTO el directly — the house convention sets `el.className`
                     // on the passed element itself (no wrapper), so el/host IS the widget's root. Measuring
                     // a child instead would pick up a FLEX ITEM's shrink-to-fit width on any widget whose
                     // root centers its children (`align-items:center`), which is not what this test means
                     // to check.
                     const r = host.getBoundingClientRect();
                     return { threw: null, width: r.width };
                   }""", [wid, data_by_id[wid]])
            out[wid] = {**res, "errors": list(errors)}

        browser.close()
    return out


def test_every_widget_renders_with_no_page_errors(widths):
    broken = {wid: m["errors"][0][:160] for wid, m in widths.items() if m.get("threw") or m["errors"]}
    assert not broken, f"widgets that failed to render at all: {broken}"


@pytest.mark.parametrize("wid", widget_ids())
def test_the_root_tracks_a_wide_card_instead_of_capping_itself(wid, widths):
    """The direct regression guard for the operator's report: BEFORE this fix, mensajeria measured ~480px on a
    900px card (its old `width:min(480px,92vw)`); agenda/contactos/musica/clock/timer/search/imagenes/navegador
    carried the identical pattern at their own caps (440-920px, all comfortably under 900*0.9=810)."""
    m = widths.get(wid) or {}
    if m.get("threw") or m.get("errors"):
        pytest.skip(f"{wid} failed to render — see test_every_widget_renders_with_no_page_errors")
    width = m.get("width") or 0
    floor = CARD_WIDTH * MIN_FRACTION
    assert width >= floor, (
        f"{wid}'s root measured {width:.0f}px on a {CARD_WIDTH}px card (needs >= {floor:.0f}px) — it is "
        f"capping itself instead of using the width the operator gave it")
