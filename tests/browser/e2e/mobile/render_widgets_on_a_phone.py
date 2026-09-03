"""Every SYSTEM widget rendered at phone width, and MEASURED (V2-574).

WHY THIS EXISTS: `widgets/AGENTS.md` — the house style every widget is built against, by a human or by the
agent — said `width:min(620px,90vw)`-ish, "Prefer horizontal / grid layouts", "NEVER a tall single broken
column". That is desktop advice, and on a 390px phone a single column is the CORRECT layout. Nothing in the
repo had ever measured a widget at phone width: node 4.18 checks the shell's contract, 4.19 the dock's pixels,
4.87 the deck's navigation — the CARDS' CONTENTS were never looked at. So this is the missing measurement, and
it is a measurement rather than a read of the stylesheets, because "the CSS says max-width" and "nothing sticks
out of a 390px screen" are different claims.

WHAT IT DOES: for each widget with a `widget.js`, the REAL module is mounted with the REAL `view_data()` output
inside a container that reproduces the deck card's box (390px wide, the `.zm-scroll > *` padding, top-aligned).
Then four things are measured, all of them symptoms an operator would report as "it looks broken on the phone":

  1. HORIZONTAL OVERFLOW of the card — the phone's own body must never scroll sideways. Wide content is allowed,
     but it has to scroll INSIDE its own box (`overflow-x:auto`), which is what this distinguishes.
  2. Anything ESCAPING the screen — an element whose box ends past 390px or starts before 0.
  3. TAP TARGETS under 40px — the desktop's 26-30px icons assume a mouse's pixel of precision.
  4. INPUTS under 16px of font-size — below that, iOS Safari zooms the page on focus and the fixed layout never
     recovers. It is the one rule in this file that is not about how it looks but about it becoming unusable.

DATA IS REAL, and READ-ONLY: `view_data()` is the same call the widget harness already makes. Nothing is
written, no canvas state is touched, and the operator's live engine is never driven — the page is built here.

Run:  ./.venv/bin/python tests/browser/e2e/mobile/render_widgets_on_a_phone.py
"""
import json
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
sys.path.insert(0, ENGINE)

W, H = 390, 844
MIN_TAP = 40           # the shell's own rule is 44; 40 leaves room for a border-box rounding, not for a design
MIN_INPUT_FONT = 16    # below this iOS zooms on focus
THIN_HTML = 900        # rendered markup under this reads as an empty/near-empty state, not a full layout

fails = []
thin = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def widget_ids():
    root = os.path.join(ENGINE, "widgets")
    out = []
    for name in sorted(os.listdir(root)):
        d = os.path.join(root, name)
        if name.startswith(("_", ".")) or not os.path.isdir(d):
            continue
        if os.path.exists(os.path.join(d, "widget.js")) and os.path.exists(os.path.join(d, "manifest.json")):
            out.append(name)
    return out


def widget_data(wid):
    """The widget's own view_data(), imported the way the harness does. Never raises — a widget whose data
    layer is unavailable still has to RENDER (its empty state is part of the contract)."""
    try:
        import importlib
        mod = importlib.import_module(f"widgets.{wid}.data")
        fn = getattr(mod, "view_data", None)
        return fn("") if callable(fn) else {}
    except Exception:
        return {}


def deck_css():
    """The card's REAL stylesheet, lifted out of Deck.js.

    Deck.js injects its CSS from a template literal at runtime, so there is no file to link — and copying those
    rules in here would be a second source of truth that drifts the first time the card's padding changes. The
    harness therefore reads the module and extracts the block, which means this measurement always runs against
    the box the phone actually renders."""
    src = open(os.path.join(ENGINE, "frontend", "mobile", "app", "shell", "Deck.js"), encoding="utf-8").read()
    i = src.index("s.textContent = `") + len("s.textContent = `")
    return src[i:src.index("`;", i)]


# ── FILLED FIXTURES ─────────────────────────────────────────────────────────────────────────────────────────
# An empty widget cannot overflow: nothing lays out, so a green measurement on an empty state measures almost
# nothing. Nine of the fourteen rendered empty against the operator's own store on 2026-09-04 — including
# `results`, which is the card every errand delivers into and the one with tabs. So the widgets whose empty
# state is the DEFAULT get a filled variant, shaped from their real `view_data()` keys and deliberately hostile
# to a narrow screen: long unbroken titles, a URL with no spaces, many chips, a grid with enough items to wrap.
# Anything not listed here is measured with whatever the operator's store holds and reported as thin.
FIXTURES = {
    "results": {
        "title": "Restaurantes con estrella en Soria y alrededores para comer mañana al mediodía",
        "subtitle": "12 sitios · 4 fuentes", "note": "",
        "items": [{"title": f"Restaurante {n} — Baltasar el Barrio de la Estación",
                   "subtitle": "Soria capital · 4,6 ★ (1.284 reseñas)",
                   "url": "https://www.eltenedor.es/restaurante/baltasar-barrio-estacion-soria/123456",
                   "price": "45-60 €", "meta": "Cocina castellana", "phone": "975 23 01 94"} for n in range(1, 13)],
        "sources": [{"title": "TheFork", "url": "https://www.eltenedor.es/ciudad/soria", "status": "ok", "n": 8},
                    {"title": "Google Maps", "url": "https://maps.google.com/?q=restaurantes+soria", "status": "ok", "n": 4},
                    {"title": "TripAdvisor", "url": "https://www.tripadvisor.es/Restaurants-g187508", "status": "failed", "n": 0}],
        "summary": {"text": "Doce restaurantes con reserva online y valoración por encima de 4,3."},
        "criteria": {"hard": ["Soria", "mañana 14:00", "≥ 4 estrellas"], "soft": ["reserva online"]},
        "counts": {"shown": 12, "sources": 3, "sources_ok": 2, "sources_failed": 1, "from_cache": 0},
    },
    "imagenes": {"title": "Ferrari F40", "query": "ferrari f40", "source": "web", "n": 12, "i": 0,
                 "current": {"url": "https://example.invalid/f40-01.jpg", "title": "Ferrari F40 1987",
                             "thumb": "https://example.invalid/f40-01-t.jpg", "source": "example.invalid"},
                 "items": [{"url": f"https://example.invalid/f40-{n:02d}.jpg", "title": f"Ferrari F40 — vista {n}",
                            "thumb": f"https://example.invalid/f40-{n:02d}-t.jpg",
                            "source": "example.invalid"} for n in range(1, 13)]},
    "documento": {"kind": "markdown", "title": "Acta de la reunión del comité de dirección",
                  "subtitle": "4 de septiembre · 6 asistentes", "empty": False, "chars": 900, "updated": 0,
                  "src": "", "source": "memoria",
                  "body": ("# Acuerdos\n\n" + "\n".join(f"- Punto {n}: se aprueba por unanimidad y se "
                           f"traslada a la siguiente sesión ordinaria." for n in range(1, 14)))},
    # The two GRIDS, which are where a narrow screen usually breaks: a tile row that does not wrap pushes the
    # card sideways, and a long unbroken filename is the classic overflow nobody notices until a phone.
    "archivos": {"provider": "drive", "providers": ["drive"], "connected": True, "folder_id": "root",
                 "trail": [{"id": "root", "name": "Mi unidad"}, {"id": "f1", "name": "Documentos de trabajo 2026"}],
                 "entries": ([{"id": f"d{n}", "name": f"Carpeta de proyecto {n}", "kind": "folder",
                               "mimeType": "application/vnd.google-apps.folder", "size": 0} for n in range(1, 4)]
                             + [{"id": f"f{n}", "name": f"Presupuesto_definitivo_revisado_v{n}_SIN_ESPACIOS.xlsx",
                                 "kind": "file", "mimeType": "application/vnd.ms-excel",
                                 "size": 1048576 * n} for n in range(1, 10)]),
                 "next": "", "query": "", "selected": None, "mode": "list", "panel": "", "error": "",
                 "reason": "", "count": 12},
    "fotos": {"connected": True, "app_configured": True, "session_pending": False, "years": [2026, 2025],
              "items": [{"id": f"p{n}", "thumb": f"https://example.invalid/t{n}.jpg",
                         "url": f"https://example.invalid/p{n}.jpg", "date": "2026-08-14T10:22:00Z",
                         "year": 2026, "w": 4032, "h": 3024} for n in range(1, 25)],
              "cursor": 0, "has_more": True, "total": 24, "active_filter": {}, "error": "", "reason": "",
              "updated": 0},
    "timer": {"remaining": 754, "target_seconds": 900, "label": "Pasta", "running": True, "finished": False},
    "navegador": {"mode": "page", "url": "https://www.eltenedor.es/restaurante/baltasar-barrio-estacion-soria/123456",
                  "title": "Baltasar — Barrio de la Estación · Reservar mesa", "rev": 3, "loading": False,
                  "error": "", "can_back": True, "can_forward": False, "updated": "2026-09-04T00:52:00+00:00"},
}


PAGE = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<link rel="stylesheet" href="/f/app/core/palette.css">
<link rel="stylesheet" href="/f/app/styles.css">
<link rel="stylesheet" href="/f/mobile/app/styles.css">
<style>
  html,body{margin:0;padding:0;background:var(--hb-bg,#fff);color:var(--hb-ink,#0d1622);
    font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial}
  /* --dock-h comes from the mobile stylesheet; the dock itself is not mounted here, so the card simply ends
     where it would end on the phone. */
</style>
<style id="deck-css">%(DECK)s</style>
<div class="zm-card live"><div class="zm-scroll"></div></div>
"""

MEASURE = """(root) => {
  const scroll = document.querySelector('.zm-scroll');
  const vw = window.innerWidth;
  const over = Math.max(0, scroll.scrollWidth - scroll.clientWidth);
  // WHO sticks out, and whether it is inside a box that scrolls on its own (which is legitimate: a wide table
  // in an overflow-x:auto wrapper is the correct answer, a wide table that pushes the page is not).
  const escapees = [];
  for (const el of root.querySelectorAll('*')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.right <= vw + 1 && r.left >= -1) continue;
    let scrollable = false;
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if ((ox === 'auto' || ox === 'scroll') && p.clientWidth <= vw + 1) { scrollable = true; break; }
    }
    if (scrollable) continue;
    escapees.push({ tag: el.tagName.toLowerCase(), cls: String(el.className || '').slice(0, 40),
                    left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width) });
  }
  const small = [];
  for (const el of root.querySelectorAll('button, a[href], input, select, textarea, [role=button], [onclick]')) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;          // hidden controls are not tap targets
    if (Math.min(r.width, r.height) < %(MIN_TAP)d)
      small.push({ tag: el.tagName.toLowerCase(), cls: String(el.className || '').slice(0, 30),
                   w: Math.round(r.width), h: Math.round(r.height) });
  }
  const tinyInputs = [];
  for (const el of root.querySelectorAll('input, textarea, select')) {
    const fs = parseFloat(getComputedStyle(el).fontSize) || 0;
    if (fs && fs < %(MIN_INPUT_FONT)d)
      tinyInputs.push({ tag: el.tagName.toLowerCase(), cls: String(el.className || '').slice(0, 30), fs });
  }
  return { over, escapees: escapees.slice(0, 6), nEscapees: escapees.length,
           small: small.slice(0, 6), nSmall: small.length, tinyInputs: tinyInputs.slice(0, 4),
           painted: root.getBoundingClientRect().height > 0, html: root.innerHTML.length };
}"""


def main():
    ids = widget_ids()
    data_by_id = {wid: (FIXTURES[wid] if wid in FIXTURES else widget_data(wid)) for wid in ids}
    print(f"measuring {len(ids)} widgets at {W}x{H} "
          f"({len(FIXTURES)} with a filled fixture): {', '.join(ids)}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": W, "height": H}, device_scale_factor=3,
                                  has_touch=True, is_mobile=True)

        # Serve the frontend and every widget module straight off disk: no engine, no network, no canvas.
        def route(r):
            path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("?")[0]
            if path in ("page", ""):
                # The page needs a real ORIGIN: with set_content() the document is about:blank and a bare
                # `/widgets/<id>/widget.js` import specifier cannot resolve at all (measured: 14 of 14 failed
                # to resolve before this). Any host works — nothing leaves the process, every request is
                # fulfilled from disk below.
                return r.fulfill(status=200, body=PAGE % {"DECK": deck_css()},
                                 headers={"content-type": "text/html; charset=utf-8"})
            if path.startswith("f/"):
                fp = os.path.join(ENGINE, "frontend", path[2:])
            elif path.startswith("widgets/"):
                fp = os.path.join(ENGINE, path)
            else:
                return r.fulfill(status=404, body="")
            if not os.path.isfile(fp):
                return r.fulfill(status=404, body="")
            ct = ("text/css" if fp.endswith(".css") else
                  "application/javascript" if fp.endswith(".js") else
                  "application/json" if fp.endswith(".json") else "text/plain")
            with open(fp, "rb") as fh:
                r.fulfill(status=200, body=fh.read(), headers={"content-type": ct})

        page = ctx.new_page()
        page.route("**/*", route)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))

        for wid in ids:
            del errors[:]
            page.goto("http://widgets.test/page", wait_until="load")
            page.wait_for_timeout(120)
            res = page.evaluate(
                """async ([wid, data]) => {
                     const host = document.createElement('div');
                     document.querySelector('.zm-scroll').appendChild(host);
                     const ctx = { action: async () => ({}), close: () => {}, top: () => {}, running: true };
                     try {
                       const mod = await import(`/widgets/${wid}/widget.js`);
                       await mod.render(host, data, ctx);
                     } catch (e) { return { threw: String(e && e.message || e) }; }
                     return { threw: null };
                   }""", [wid, data_by_id[wid]])
            if res.get("threw"):
                check(f"{wid}: renders", False, res["threw"])
                continue
            page.wait_for_timeout(220)          # give a widget that animates or defers its first paint a beat
            m = page.evaluate(MEASURE % {"MIN_TAP": MIN_TAP, "MIN_INPUT_FONT": MIN_INPUT_FONT},
                              page.query_selector(".zm-scroll > *"))
            check(f"{wid}: renders", m["painted"] and m["html"] > 0, json.dumps(m)[:200])
            # HOW MUCH was actually on screen. A widget whose store is empty renders its EMPTY STATE, which is a
            # legitimate render but a thin measurement: nothing lays out, so nothing can overflow. Reporting it
            # keeps "all 14 fit a phone" from claiming more than it measured — the ones marked here were checked
            # with little content and deserve a second look when they have data.
            if m["html"] < THIN_HTML:
                thin.append(f"{wid} ({m['html']}B)")
            check(f"{wid}: the card does not scroll sideways", m["over"] <= 1,
                  f"{m['over']}px of horizontal overflow · first offenders: {json.dumps(m['escapees'])}")
            check(f"{wid}: nothing escapes the screen", m["nEscapees"] == 0,
                  f"{m['nEscapees']} element(s) outside 0..{W}px: {json.dumps(m['escapees'])}")
            check(f"{wid}: every control is at least {MIN_TAP}px", m["nSmall"] == 0,
                  f"{m['nSmall']} small control(s): {json.dumps(m['small'])}")
            check(f"{wid}: inputs are >= {MIN_INPUT_FONT}px (iOS zooms below that)", not m["tinyInputs"],
                  json.dumps(m["tinyInputs"]))
            if errors:
                check(f"{wid}: no page errors", False, errors[0][:160])

        browser.close()

    if thin:
        print(f"\n⚠️  measured with little or no content (empty state): {', '.join(thin)}")
    print(f"\n{len(fails)} FAILURE(S)" if fails else "\nALL OK")
    return 1 if fails else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(2)
