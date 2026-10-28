"""The two-screen check — one computer and one phone on the same agent, for ANY widget (V2-792).

The operator runs one agent on his computer and his phone at once, and every widget declares how it lives across
them (`"screens"`, `widgets/screen_policy.py`). This opens TWO real browsers against one preview of the engine's own
routers — a desktop window and a phone-sized one, each with its own storage and its own event stream — pushes the
events a real turn produces through the engine's REAL stream, and reads what each screen DID:

  shared  · asked on the computer → it opens on the computer, the phone shows a chip and does not open it;
          · asked on the phone too → it is open on BOTH (a reflection is never taken away).
  single  · asked on the computer → it opens on the computer, the phone shows a chip;
          · asked on the phone while the computer has it → the computer closes its copy, the phone opens it.

Run it by hand on one widget (or several), headless or with the two windows visible:

    ./.venv/bin/python tests/browser/e2e/mobile/two_screens.py youtube agenda
    ./.venv/bin/python tests/browser/e2e/mobile/two_screens.py my-widget --headed

…or through the widget harness (`python -m tests.widget_harness --two-screens <id>`). Node 4.270 runs it over the whole
catalogue, so a widget added tomorrow is checked without anyone writing a test for it. What a browser cannot
measure — a real phone, a real microphone, the sound — is the operator's manual pass:
`.meshkore/docs/ops/zaelar-two-screen-test.md`.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request

ENGINE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
DESK, PHONE = "desktop:twoscrdesk", "mobile:twoscrphone"

PREVIEW = '''
import sys; sys.path.insert(0, %r)
import uvicorn
from fastapi import FastAPI, Body
from fastapi.staticfiles import StaticFiles
from server import pages, i18n_api, voice_api, canvas_api, screens_api, livekit_api
from widgets import server_api as widgets_api
from voice import observer
app = FastAPI()
for r in (livekit_api.router, pages.router, i18n_api.router, voice_api.router, canvas_api.router, screens_api.router,
          widgets_api.router):
    app.include_router(r)
@app.post("/__emit")
def _emit(ev: dict = Body(...)):
    observer.emit(ev.pop("kind"), ev.pop("label", ""), text=ev.pop("text", ""), role=ev.pop("role", ""), extra=ev)
    return {"ok": True}
app.mount("/static", StaticFiles(directory=%r), name="static")
uvicorn.run(app, host="127.0.0.1", port=%d, log_level="critical")
'''

# The host's show/close are recorded and NOT executed: this measures where each screen sends a card, not how the card
# paints (every widget has its own render test). `list()` answers from what this screen was told to open.
SPY = """() => { const h = window.__zaelarDesktop; if (!h || window.__spy) return !!h; window.__spy = true;
  window.__open = new Set(); window.__shows = []; window.__closes = [];
  h.show = (id) => { window.__shows.push(String(id)); window.__open.add(String(id)); return Promise.resolve(); };
  h.close = (id) => { window.__closes.push(String(id)); window.__open.delete(String(id)); };
  h.list = () => [...window.__open]; return true; }"""
READ = """() => { const painted = e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return { shows: window.__shows, closes: window.__closes, open: [...window.__open],
           chips: [...document.querySelectorAll('.ew-chip')].filter(painted).map(e => (e.textContent || '').trim()) }; }"""
RESET = """async () => { window.__open.clear(); window.__shows.length = 0; window.__closes.length = 0;
  (await import('/static/app/core/store.js?v=2')).setElsewhere([]); return true; }"""


def _free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class TwoScreens:
    """A preview of the engine + a desktop page + a phone page. Use as a context manager."""

    def __init__(self, headed: bool = False, desk_init: str = "", spy: bool = True):
        self.headed = headed
        self.desk_init = desk_init      # extra JS run before the desktop page loads (e.g. the orb docked in the bar)
        self.spy = spy                  # record show/close instead of executing them (the catalogue check needs it)
        self.base = ""
        self._proc = self._pw = self._browser = None
        self.desk = self.phone = None
        self.errors: list[str] = []

    # ── lifecycle ──────────────────────────────────────────────────────────────────────────────────────────────
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        port = _free_port()
        self._proc = subprocess.Popen(
            [sys.executable, "-c", PREVIEW % (ENGINE, os.path.join(ENGINE, "frontend"), port)], cwd=ENGINE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            # a temp workspace has no language chosen; the gate would keep the agent stopped
            env={**os.environ, "ZAELAR_LANGUAGE_GATE": "0"})
        deadline = time.time() + 60.0
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); break
            except OSError:
                time.sleep(0.5)
        else:
            self.__exit__(None, None, None)
            raise RuntimeError("preview server never came up in 60 s")
        self.base = f"http://127.0.0.1:{port}"
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=not self.headed, args=["--no-sandbox"])
        self.desk = self._open(DESK, "/", {"width": 1280, "height": 800}, self.desk_init)
        self.phone = self._open(PHONE, "/m", {"width": 390, "height": 844})
        for pg in (self.desk, self.phone):
            pg.wait_for_timeout(2500)
            pg.evaluate("() => document.querySelectorAll('.boot-ovl, .lang-onb, .lang-onb-veil, .zm-held')"
                        ".forEach(e=>e.remove())")
            if self.spy:
                assert pg.evaluate(SPY), "the page exposes no host (window.__zaelarDesktop)"
        return self

    def __exit__(self, *exc):
        for x in (self._browser,):
            try:
                x and x.close()
            except Exception:  # noqa: BLE001 — teardown of a browser that may already be gone
                self.errors.append("browser close failed")
        try:
            self._pw and self._pw.stop()
        except Exception:  # noqa: BLE001
            self.errors.append("playwright stop failed")
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        return False

    def _open(self, dev: str, path: str, viewport: dict, extra: str = ""):
        ctx = self._browser.new_context(viewport=viewport)
        did = dev.split(":", 1)[1]
        # The preview has no language chosen; the guard keeps its first-run takeover from wiping and reloading the
        # page the moment a test switches the agent off (that takeover is first-run.js's, tested on its own).
        ctx.add_init_script(f"try{{localStorage.setItem('hb_device_id','{did}');localStorage.setItem('hb_lang','en');"
                            "sessionStorage.setItem('hb_first_run_takeover','1');" + extra + "}catch(_){}")
        pg = ctx.new_page()
        pg.on("pageerror", lambda e, d=dev: self.errors.append(f"{d}: {e}"))
        pg.goto(self.base + path, wait_until="domcontentloaded")
        return pg

    # ── driving ────────────────────────────────────────────────────────────────────────────────────────────────
    def emit(self, ev: dict) -> None:
        req = urllib.request.Request(self.base + "/__emit", data=json.dumps(ev).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()

    def ask(self, dev: str, card: str, trace: str) -> None:
        """What a real turn does: the line from `dev`, then the card it opens."""
        self.emit({"kind": "transcript", "label": "final", "text": f"open {card}", "role": "user", "dev": dev,
                   "trace": trace})
        self.emit({"kind": "widget", "label": "show", "id": card, "src": "flash", "trace": trace})

    def read(self):
        return self.desk.evaluate(READ), self.phone.evaluate(READ)

    def settle(self, pred, budget: float = 6.0):
        end = time.time() + budget
        while time.time() < end:
            if pred(*self.read()):
                return True
            time.sleep(0.15)
        return bool(pred(*self.read()))

    def reset(self) -> None:
        for pg in (self.desk, self.phone):
            pg.evaluate(RESET)

    # ── the check ──────────────────────────────────────────────────────────────────────────────────────────────
    def policy(self, wid: str) -> str:
        rows = json.loads(urllib.request.urlopen(self.base + "/widgets", timeout=10).read()).get("widgets") or []
        return next((str(w.get("screens") or "shared") for w in rows if w.get("id") == wid), "")

    def check(self, wid: str) -> list[tuple[bool, str]]:
        """Every expectation of this widget's declared policy, as (passed, what)."""
        out: list[tuple[bool, str]] = []
        pol = self.policy(wid)
        if not pol:
            return [(False, f"{wid} is not in the catalogue")]
        self.reset()
        self.ask(DESK, wid, f"two-{wid}-1")
        out.append((self.settle(lambda d, p: wid in d["open"]), "asked on the computer → opens on the computer"))
        d, p = self.read()
        out.append((wid not in p["shows"], "…and the phone does not open it"))
        out.append((self.settle(lambda d, p: any("computer" in c.lower() for c in p["chips"])),
                    "…and the phone shows a chip naming the computer"))
        # Two turns are seconds apart in life; within 150 ms the observer folds two identical `show`s into one
        # (its flood guard, `voice/observer.emit`), which is right for a flood and wrong for this test.
        time.sleep(0.4)
        self.ask(PHONE, wid, f"two-{wid}-2")
        if pol == "single":
            out.append((self.settle(lambda d, p: wid in d["closes"] and wid in p["open"]),
                        "single · asked on the phone → the computer closes its copy and the phone opens it"))
            out.append((self.settle(lambda d, p: any("phone" in c.lower() for c in d["chips"])),
                        "single · the computer keeps a chip naming the phone"))
        else:
            out.append((self.settle(lambda d, p: wid in p["open"]), "shared · asked on the phone → it opens there"))
            time.sleep(0.6)
            d, p = self.read()
            out.append((wid in d["open"] and wid not in d["closes"], "shared · …and stays open on the computer"))
        return out


def main(argv: list[str]) -> int:
    headed = "--headed" in argv
    ids = [a for a in argv if not a.startswith("--")]
    failures = 0
    with TwoScreens(headed=headed) as ts:
        if not ids:
            rows = json.loads(urllib.request.urlopen(ts.base + "/widgets", timeout=10).read()).get("widgets") or []
            ids = [w["id"] for w in rows if not w.get("transient")]
        for wid in ids:
            res = ts.check(wid)
            bad = [r for r in res if not r[0]]
            failures += len(bad)
            print(f"{'✓' if not bad else '✗'} {wid}  ({ts.policy(wid) or '?'})")
            for ok, what in res:
                print(f"    {'✓' if ok else '✗'} {what}")
            if headed:
                time.sleep(1.5)
        if ts.errors:
            print("page errors:", *ts.errors, sep="\n  ")
            failures += len(ts.errors)
    print(f"\n{'OK' if not failures else 'FAIL'} — {len(ids)} widget(s) on two screens, {failures} failing check(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
