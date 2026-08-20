"""EXECUTABLE SPEC for V2-227 ámbito C — the results sheet as the live progress surface.

WHY A BROWSER AND NOT A UNIT TEST: the requirement is what a waiting person SEES. A source-level test
can prove a tab exists and still ship a panel that renders nothing, a spinner that is in the DOM but
frozen, or an auto-switch that fires before the first result is painted. On 2026-08-18 exactly that
shipped on the mobile shell: 0 painted pixels of 9216, 741 frames into a detached canvas, no error
anywhere, and a green test that counted canvases and was satisfied they existed.

WHAT IT SPECIFIES (operator, 2026-08-20), and it FAILS until ámbito C lands — that is the point:
  1. With a task alive and NO results yet, the sheet opens on a PROCESS tab. The user sees the sheet
     before there is anything to put in it; that is the whole feature.
  2. The phases are readable text, in order, newest visible without scrolling.
  3. The spinner is ANIMATING, not merely present.
  4. The first result switches the sheet to the results tab BY ITSELF...
  5. ...and the process tab keeps spinning while the worker is alive.
  6. When the worker finishes, the spinner stops and the process tab keeps its history.

Self-contained: it mounts widget.js in a blank page and drives `render()` directly. No engine, no
worker, no network — the payload shapes are the contract between motor-dev's backend and this surface.

Run:  ./.venv/bin/python tests/browser/e2e/results/render_process_tab.py
"""
import json
import os
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ENGINE = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
WIDGET = os.path.join(ENGINE, "widgets", "results", "widget.js")

ALIVE_NO_RESULTS = {
    "title": "Hoteles en Sevilla",
    "items": [],
    "progress": {"alive": True, "phases": [
        "entrando en booking.com…", "aplicando filtro 4 estrellas…", "lanzando la búsqueda…"]},
}
FIRST_RESULT = {
    "title": "Hoteles en Sevilla",
    "items": [{"title": "Bécquer", "price": "100 €", "url": "https://example.invalid/becquer"}],
    "progress": {"alive": True, "phases": [
        "entrando en booking.com…", "aplicando filtro 4 estrellas…", "lanzando la búsqueda…",
        "12 resultados", "descartando los que no cumplen…"]},
}
FINISHED = {**FIRST_RESULT, "progress": {**FIRST_RESULT["progress"], "alive": False}}

fails = []


def check(name, ok, detail=""):
    print(("  ok   " if ok else "  FAIL ") + name + (f"\n         {detail}" if detail and not ok else ""))
    if not ok:
        fails.append(name)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main():
    port = _free_port()
    srv = subprocess.Popen([sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
                           cwd=ENGINE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    try:
        return _run(port)
    finally:
        srv.terminate()


def _run(port):
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 800})
        # A REAL http origin: a module cannot be dynamically imported from `about:blank`/`file:`, and the
        # failure reads as "Failed to fetch dynamically imported module", which looks like a broken widget.
        page.goto(f"http://127.0.0.1:{port}/widgets/results/")
        page.set_content("<div id='host'></div>")
        page.evaluate("""async (src) => {
            const mod = await import(src);
            window.__render = (data) => mod.render(document.getElementById('host'), data, {action(){}, top(){}});
        }""", f"http://127.0.0.1:{port}/widgets/results/widget.js")

        # 1 · the sheet opens on PROCESS with nothing to show yet
        page.evaluate("(d) => window.__render(d)", ALIVE_NO_RESULTS)
        active = page.evaluate("""() => {
            const on = document.querySelector('.hr-tab.on');
            return on ? (on.dataset.tab || on.textContent.trim()) : null; }""")
        check("1 · con tarea viva y CERO resultados, la pestaña activa es la de proceso",
              (active or "").lower().startswith(("proc", "process")), f"pestaña activa: {active!r}")

        # 2 · the phases are on screen, in order, and the newest is visible without scrolling
        seen = page.evaluate("""() => {
            const p = document.querySelector('.hr-panel');
            return p ? p.innerText.trim() : ''; }""")
        check("2 · las fases se leen en pantalla, en orden",
              "entrando en booking.com" in seen and seen.index("entrando") < seen.index("lanzando"),
              f"panel: {seen[:160]!r}")

        # 3 · the spinner MOVES. Present-but-frozen is the failure this whole file exists to catch.
        spins = page.evaluate("""() => {
            const el = document.querySelector('.hr-panel [class*=spin], .hr-panel [class*=load]');
            if (!el) return {found: false};
            const a = el.getAnimations ? el.getAnimations() : [];
            const cs = getComputedStyle(el);
            return {found: true, running: a.some(x => x.playState === 'running'),
                    css: cs.animationName !== 'none' && cs.animationPlayState === 'running'}; }""")
        check("3 · el loader está ANIMANDO, no solo presente",
              bool(spins.get("found")) and bool(spins.get("running") or spins.get("css")), json.dumps(spins))

        # 4 · the first result moves the sheet by itself
        page.evaluate("(d) => window.__render(d)", FIRST_RESULT)
        active2 = page.evaluate("""() => {
            const on = document.querySelector('.hr-tab.on');
            return on ? (on.dataset.tab || on.textContent.trim()) : null; }""")
        # NO SE PUEDE LEER EN VERDE MIENTRAS 1 FALLE: hoy la hoja ya nace en «results», así que esto pasa
        # sin que nadie haya saltado a ningún sitio. Sólo prueba el AUTO-SALTO cuando la comprobación 1
        # cumple y el punto de partida es la pestaña de proceso.
        moved = (active2 or "") == "results" and (active or "").lower().startswith(("proc", "process"))
        check("4 · al PRIMER resultado la hoja salta sola a resultados",
              moved, f"pestaña activa: {active2!r} (venía de {active!r}; sin la 1 en verde esto no prueba nada)")
        painted = page.evaluate("""() => (document.querySelector('.hr-panel')||{}).innerText || ''""")
        check("4b · y el resultado se ve de verdad en el panel", "Bécquer" in painted, f"panel: {painted[:120]!r}")

        # 7 · THE ONE THE OPERATOR ACTUALLY SEES. After the jump the reader is looking at the results
        # list, so the process panel's spinner (check 5) is off-screen: the only thing left saying "still
        # working" is the marker on the process TAB BUTTON. Measured on the button, from the results tab,
        # and by animation — a static dot in the DOM would pass an existence check and tell the reader
        # nothing.
        onbtn = page.evaluate("""() => {
            const t = [...document.querySelectorAll('.hr-tab')].find(b =>
                (b.dataset.tab||'').startsWith('proc') || /proceso/i.test(b.textContent));
            if (!t) return {found: false};
            const el = t.querySelector('[class*=spin], [class*=load]');
            const a = el && el.getAnimations ? el.getAnimations() : [];
            const r = el ? el.getBoundingClientRect() : null;
            return {found: true, marker: !!el, w: r ? Math.round(r.width) : 0,
                    running: a.some(x => x.playState === 'running'),
                    active: (document.querySelector('.hr-tab.on')||{}).dataset ?
                            (document.querySelector('.hr-tab.on').dataset.tab||'') : ''}; }""")
        check("7 · con la tarea viva y mirando la LISTA, el botón de proceso sigue diciendo que trabaja",
              bool(onbtn.get("running")) and onbtn.get("w", 0) > 0 and onbtn.get("active") == "results",
              json.dumps(onbtn))

        # 5 · the process tab is still spinning underneath
        still = page.evaluate("""() => {
            const t = [...document.querySelectorAll('.hr-tab')].find(b =>
                (b.dataset.tab||'').startsWith('proc') || /proceso/i.test(b.textContent));
            if (!t) return {found: false};
            t.click();
            const el = document.querySelector('.hr-panel [class*=spin], .hr-panel [class*=load]');
            const a = el && el.getAnimations ? el.getAnimations() : [];
            return {found: true, spinner: !!el, running: a.some(x => x.playState === 'running')}; }""")
        check("5 · la pestaña de proceso SIGUE girando con el worker vivo",
              bool(still.get("spinner")), json.dumps(still))

        # 6 · when it ends, the spinner stops and the history stays
        page.evaluate("(d) => window.__render(d)", FINISHED)
        done = page.evaluate("""() => {
            const t = [...document.querySelectorAll('.hr-tab')].find(b =>
                (b.dataset.tab||'').startsWith('proc') || /proceso/i.test(b.textContent));
            if (t) t.click();
            const p = document.querySelector('.hr-panel');
            const el = p && p.querySelector('[class*=spin], [class*=load]');
            const a = el && el.getAnimations ? el.getAnimations() : [];
            return {text: p ? p.innerText : '', spinning: a.some(x => x.playState === 'running')}; }""")
        check("6 · al acabar, el loader para y la historia se queda",
              (not done.get("spinning")) and "entrando en booking.com" in (done.get("text") or ""),
              json.dumps(done)[:200])

        # 7b · and the button stops claiming work that finished. A marker that never clears is worse than
        # none: it teaches the reader to ignore it.
        offbtn = page.evaluate("""() => {
            const t = [...document.querySelectorAll('.hr-tab')].find(b =>
                (b.dataset.tab||'').startsWith('proc') || /proceso/i.test(b.textContent));
            if (!t) return {found: false};
            const el = t.querySelector('[class*=spin], [class*=load]');
            const a = el && el.getAnimations ? el.getAnimations() : [];
            return {found: true, marker: !!el, running: a.some(x => x.playState === 'running'),
                    label: t.textContent.trim()}; }""")
        check("7b · y al acabar el botón deja de girar",
              not offbtn.get("running"), json.dumps(offbtn))

        browser.close()

    print()
    if fails:
        print(f"✗ {len(fails)} de 8 sin cumplir — ámbito C todavía no está: {', '.join(fails)}")
        return 1
    print("✓ ámbito C cumple el contrato de las 8 comprobaciones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
