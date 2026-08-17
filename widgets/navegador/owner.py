#
# owner.py — live BACKEND for the "navegador" widget (kind:"backed", INI-016). It is the ONLY writer to
# widgets/_data/navegador/ (widget-app contract: zaelar-modules.md §Widget-apps). The supervisor
# (widgets/supervisor.py) starts it in the server loop and passes mailbox commands to handle().
#
# Why a backend instead of an iframe: almost no website (Google, Wallapop, RAE, stores...) allows being embedded in
# an <iframe> (they send X-Frame-Options/CSP frame-ancestors). So the REAL browser lives here (headless Chromium via
# Playwright): it navigates the actual page on the server, screenshots it, and the widget displays that capture.
# Operator clicks/scroll/typing are mapped back to page coordinates → Chromium → new capture. Because the backend
# drives the page through code, VOICE and AUTOMATION can be plugged on top later (that is the goal: "open Wallapop
# and find me a motorcycle under €5000 from 2020 onward").
#
# YouTube is the EXCEPTION: a static screenshot cannot play video/audio → the video id is resolved and the widget
# mounts the real embedded player (youtube-nocookie) on the client. Everything else uses screenshots.
#
# LAZY startup: start() is cheap (it does not launch Chromium); the browser starts on the first command, so a browser
# that is never opened does not cost a Chromium process. Resilient: a failure on ONE page (bad URL, timeout) writes an
# error to state and does NOT crash the backend; the browser auto-relaunches if Chromium dies.
#
import asyncio
import os
import random
import re
import sys
from datetime import datetime, timezone
from urllib.parse import quote_plus

from loguru import logger

from .. import store

WID = "navegador"
VIEWPORT = {"width": 1280, "height": 800}
HOME = {"mode": "blank", "url": "", "title": "Nuevo navegador"}
_NAV_TIMEOUT = 20_000   # ms — goto cap; a slow website must not block the mailbox

# Cookie/consent banner selectors for auto-dismiss after navigation (best effort).
# Any failing selector is a quick no-op. Ordered from most specific to most generic.
_COOKIE_SELECTORS = [
    # OneTrust (the most common consent system in Europe)
    "#onetrust-accept-btn-handler",
    "#onetrust-reject-all-handler",
    "#onetrust-group-btn #accept-recommended-btn-handler",
    # Didomi
    ".didomi-components-button--accept",
    "#didomi-notice-agree-button",
    # Text-based buttons — Spanish variants covering Wallapop, El Pais, etc.
    "button:has-text(\"Aceptar y continuar\")",
    "button:has-text(\"Aceptar todas\")",
    "button:has-text(\"Aceptar cookies\")",
    "button:has-text(\"Aceptar\")",
    "button:has-text(\"Acepto\")",
    "button:has-text(\"Permitir\")",
    "button:has-text(\"Permitir cookies\")",
    "button:has-text(\"Permitir todas\")",
    "button:has-text(\"Continuar\")",
    "button:has-text(\"Cerrar\")",
    # Links that act like an accept button
    "a:has-text(\"Aceptar\")",
    "a:has-text(\"Acepto\")",
    # Generic class/id selectors containing 'cookie' or 'consent'
    "[class*=\"cookie\"] button",
    "[class*=\"consent\"] button",
    "[id*=\"cookie\"] button",
    "[data-testid*=\"cookie\"] button",
    # Wallapop-specific selector: its custom banner (not OneTrust)
    "button:has-text(\"Configurar\")",
    "[class*=\"CookieConsent\"] button",
    "[class*=\"cookie-consent\"] button",
    "[class*=\"cookieBanner\"] button",
    "[class*=\"consent-modal\"] button",
    # Any button INSIDE a banner/dialog with cookie text
    "[class*=\"cookie-banner\"] button",
    "[class*=\"cookies-banner\"] button",
    "[role=\"dialog\"] button:has-text(\"Aceptar\")",
    "[role=\"dialog\"] button:has-text(\"Continuar\")",
    "[aria-label*=\"cookie\" i] button",
    # Wallapop: its modal layer with specific buttons
    "div[class*=\"modal\"] button:has-text(\"Aceptar\")",
    "div[class*=\"modal\"] button:has-text(\"Continuar\")",
    # Wallapop app/store banner
    "button[aria-label=\"Cerrar\"]",
]

# Search engine: Google CAPTCHAs headless Chromium (/sorry/index) and DuckDuckGo blocks it (418) → search would break
# right where testers use it most. Bing reliably renders a NORMAL results page headless. Google remains accessible via
# `open google.com`. Configurable by env in case this changes.
_SEARCH_URL = os.environ.get("NAVEGADOR_SEARCH", "https://www.bing.com/search?q={q}")

# Live backend state (one shared Chromium). The mailbox serializes commands → no concurrency here.
_pw = None
_browser = None
_context = None
_page = None
_hist: list[str] = []   # own history for back/forward flags (Chromium moves; we derive)
_idx = -1
_rev = 0
_mouse = {"x": 0.0, "y": 0.0}   # simulated mouse position, used to move between points with a human-like trajectory
_automating = False             # True while an automator task is running → draws the cursor in the capture


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> dict:
    return store.load(WID, {**HOME, "rev": 0, "loading": False, "error": "",
                            "can_back": False, "can_forward": False, "youtube_id": "", "youtube_title": ""})


def _write(**changes) -> None:
    """The ONLY state write point → store.save emits the SSE refresh for the open card."""
    db = _read()
    db.update(changes)
    db["updated"] = _now()
    db["can_back"] = _idx > 0
    db["can_forward"] = 0 <= _idx < len(_hist) - 1
    store.save(WID, db)


def _emit(label: str, text: str = "", **extra) -> None:
    try:
        from voice.observer import emit
        emit("navegador", label, text=text, extra={"id": WID, **extra})
    except Exception:
        pass


# ── page utilities ───────────────────────────────────────────────────────────────────────────────────────────
# ACCEPT buttons for the most common CMPs (stable id/class). consentmanager.net (used by Wallapop) renders an
# <a class="cmpboxbtnyes">Aceptar todo</a>; OneTrust/Didomi have their ids. We WAIT for the CMP to inject them
# (they arrive via JS AFTER domcontentloaded — this is why the immediate attempt found nothing and the wall stayed).
_CMP_ACCEPT = (".cmpboxbtnyes", "#onetrust-accept-btn-handler", "#didomi-notice-agree-button",
               ".didomi-components-button--accept")


async def _dismiss_overlays(page) -> None:
    """Accept the cookie/consent banner that COVERS the website. CMPs inject the banner through JS after load → we
    wait for the accept button to appear (bounded) and click it; otherwise, do a quick text sweep across all frames.
    Best-effort: never raises, no-op if there is no banner (pays the timeout once per navigation)."""
    # 1) Known CMP: wait_for_selector returns AS SOON AS it appears (or cuts at timeout if the site has no banner).
    try:
        combined = ", ".join(_CMP_ACCEPT)
        btn = await page.wait_for_selector(combined, timeout=2500, state="visible")
        if btn:
            await btn.click(timeout=2000)
            _emit("dismiss_overlay", "cmp-accept")
            # WAIT until the banner is fully CLOSED before returning (otherwise the screenshot still shows the wall —
            # consentmanager close takes ~1-2s, longer than the previous fixed 0.4s sleep).
            try:
                await page.wait_for_selector(combined, state="hidden", timeout=2500)
            except Exception:
                await asyncio.sleep(1.0)
            return
    except Exception:
        pass
    # 2) Text/generic-selector fallback, in ALL frames (some CMPs live in an iframe), without waits.
    for fr in page.frames:
        for sel in _COOKIE_SELECTORS:
            try:
                btn = await fr.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click(timeout=2000)
                    await asyncio.sleep(0.3)
                    _emit("dismiss_overlay", sel)
                    return
            except Exception:
                continue


# ── lifecycle ────────────────────────────────────────────────────────────────────────────────────────────────
async def start() -> None:
    """Intentionally cheap: does not launch Chromium (lazy start on first handle). Leaves the state as 'ready'."""
    _write(loading=False, error="")
    _emit("ready", "navegador listo (Chromium se lanza al primer uso)")
    # RECOVERY after restart: tasks live in RAM and die with the process, but a HALF-FINISHED login leaves a DURABLE
    # breadcrumb in memory → on startup we remind the operator once (we cannot resume it ourselves because the task no
    # longer exists; the operator decides whether to resume). Best-effort: never breaks widget startup.
    try:
        from . import auth_memory
        pend = auth_memory.read_auth_pending()
        if pend and pend.get("sitio"):
            from voice import proactive
            await proactive.notify("navegador", f"Antes dejaste a medias el inicio de sesión en "
                                   f"{pend['sitio']}. Si quieres, lo retomamos.", kind="notify")
            auth_memory.clear_auth_pending()          # already notified → do not repeat the reminder on every startup
    except Exception:
        pass


async def stop() -> None:
    global _pw, _browser, _context, _page
    for closer in (lambda: _context and _context.close(),
                   lambda: _browser and _browser.close(),
                   lambda: _pw and _pw.stop()):
        try:
            r = closer()
            if r is not None:
                await r
        except Exception:
            pass
    _pw = _browser = _context = _page = None
    _emit("stopped")


async def _close_browser() -> None:
    """Close the browser WINDOW at the operator's request ("close the browser"), WITHOUT deleting the profile →
    cookies/session are preserved and the next navigation relaunches with the session intact. Leaves the desktop clean."""
    await stop()                                      # close the only window; the profile persists on disk
    _write(mode="blank", url="", title="Navegador cerrado", loading=False, error="",
           youtube_id="", youtube_title="")
    _emit("closed_window", "ventana cerrada (sesión guardada)")


_visible_override = None   # None = normal; True = force visible (login); False = force headless. Used by authenticate.


def _headless() -> bool:
    """HEADLESS by DEFAULT (2026-07-08): runs IN THE BACKGROUND, without a window → it does not steal the operator's
    focus/cursor (they can type on their computer while the bot automates) and it does not need to be watched —
    screenshots are enough. To SEE IT (manual driving / LOGIN), enable visible mode: store `navegador_visible=true`,
    env ZAELAR_NAVEGADOR_VISIBLE=1, or authenticate's runtime override."""
    if _visible_override is not None:      # authenticate forces visible for login, then returns to headless
        return not _visible_override
    if os.environ.get("ZAELAR_NAVEGADOR_VISIBLE", "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        import json as _json
        from config.settings import SETTINGS_FILE
        if SETTINGS_FILE.is_file():
            if (_json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {}).get("navegador_visible"):
                return False
    except Exception:
        pass
    if os.environ.get("ZAELAR_NAVEGADOR_HEADLESS", "").strip().lower() in ("0", "false", "no"):
        return False
    return True   # default: headless (in the background)


def _profile_dir() -> str:
    """PERSISTENT and ISOLATED profile (cookies/session/logins are saved on disk → no need to re-enter credentials).
    Lives inside the widget, separate from your Chrome and your 9222 automation: it NEVER shares your own profile."""
    d = os.path.join(store.data_dir(WID), "profile")
    os.makedirs(d, exist_ok=True)
    return d


def _remote_port() -> str:
    """Browser remote-debugging port — CONFIGURATION-CONTROLLABLE (the UI writes config/settings.json).
    Order: store `navegador_remote_port` → env `NAVEGADOR_REMOTE_PORT` → empty (internal pipe, no TCP port).
    NEVER uses 9222/9200 (typical operator automation ports): if someone sets them, they are ignored and it falls
    back to pipe, so it never steps on their browser. Best-effort: any read failure → env/empty."""
    val = ""
    try:
        import json as _json
        from config.settings import SETTINGS_FILE
        if SETTINGS_FILE.is_file():
            val = str((_json.loads(SETTINGS_FILE.read_text(encoding="utf-8")) or {})
                      .get("navegador_remote_port") or "").strip()
    except Exception:
        val = ""
    val = val or os.environ.get("NAVEGADOR_REMOTE_PORT", "").strip()
    return "" if val in ("9222", "9200") else val


_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled",
                "--window-size=1296,900", "--window-position=60,60"]

# BROWSE LIKE A HUMAN, not like a scraper (operator rule 2026-07-21): a DISCREET assistant that searches like a person
# and naturally passes anti-bot filters — never scraper patterns. This init script removes fingerprints that expose an
# automated Chromium (DataDome/idealista, PerimeterX, Cloudflare check these): navigator.webdriver, missing chrome
# object, empty plugins/languages, headless WebGL "SwiftShader". It combines with REAL Chrome (channel), Bezier+jitter
# mouse movement, and delayed typing that ALREADY exist. It does not hack anything: it makes a real browser, driven
# slowly, look like what it is — a person browsing.
_STEALTH_JS = """
(() => {
  try { Object.defineProperty(navigator, 'webdriver', {get: () => undefined}); } catch (e) {}
  try { window.chrome = window.chrome || { runtime: {}, app: {}, csi: () => {}, loadTimes: () => {} }; } catch (e) {}
  try { Object.defineProperty(navigator, 'languages', {get: () => ['es-ES','es','en']}); } catch (e) {}
  try { Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]}); } catch (e) {}
  try {
    const gp = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function (p) {
      if (p === 37445) return 'Intel Inc.';                      // UNMASKED_VENDOR_WEBGL
      if (p === 37446) return 'Intel Iris OpenGL Engine';        // UNMASKED_RENDERER_WEBGL (no 'SwiftShader')
      return gp.call(this, p);
    };
  } catch (e) {}
  try {
    const q = navigator.permissions && navigator.permissions.query;
    if (q) navigator.permissions.query = (p) => (p && p.name === 'notifications')
      ? Promise.resolve({state: Notification.permission}) : q(p);
  } catch (e) {}
})();
"""


async def _ensure_page():
    """ONE real window (headed) with a PERSISTENT PROFILE and lazy startup. Reuses any existing window/tab (never opens
    one window per request → no desktop clutter). Isolated profile: does not touch your Chrome or your 9222/9200
    browser (own process and instance). If the real window fails (no display), degrades to headless so the widget is
    not left dead. Lazy Playwright import: if the dependency is missing, only this widget degrades."""
    global _pw, _browser, _context, _page
    if _page is not None and not _page.is_closed():
        return _page
    from playwright.async_api import async_playwright
    if _pw is None:
        _pw = await async_playwright().start()
    if _context is None:
        # OPTIONAL debugging port chosen by env — NEVER yours (9222/9200). Empty = Playwright internal pipe
        # (zero ports, zero collisions). If you want to attach, set NAVEGADOR_REMOTE_PORT to a different port.
        args = list(_LAUNCH_ARGS)
        port = _remote_port()                         # configurable por UI (settings.json) / env; nunca 9222/9200
        if port:
            args.append(f"--remote-debugging-port={port}")
            _emit("remote_port", f"puerto de depuración {port}")

        async def _launch(headless: bool, channel: str | None):
            # channel="chrome" = the installed REAL Chrome (real-browser fingerprint, not Playwright's Chromium that
            # anti-bot systems recognize). timezone_id keeps the zone consistent with locale es-ES.
            kw = dict(headless=headless, viewport=VIEWPORT, locale="es-ES",
                      timezone_id="Europe/Madrid", user_agent=_UA, args=args)
            if channel:
                kw["channel"] = channel
            return await _pw.chromium.launch_persistent_context(_profile_dir(), **kw)

        # Prefer REAL Chrome (less detectable). If it is not installed, fall back to Playwright's Chromium; if there
        # is no display (headed fails), fall back to headless. Never leave the widget dead.
        _context = None
        for _ch in ("chrome", None):
            try:
                _context = await _launch(_headless(), _ch)
                break
            except Exception as e:
                logger.warning(f"navegador: launch channel={_ch or 'chromium'} falló "
                               f"({str(e).splitlines()[0][:100]})")
        if _context is None:
            try:
                _context = await _launch(True, None)      # last resort: headless chromium
            except Exception as e:
                logger.warning(f"navegador: headless también falló ({str(e).splitlines()[0][:100]})")
                raise
        _browser = None                               # the persistent context IS the browser (no separate object)
        try:
            await _context.add_init_script(_STEALTH_JS)   # stealth: browse like a human, not like a scraper
        except Exception:
            pass
        _context.set_default_navigation_timeout(_NAV_TIMEOUT)
        _context.set_default_timeout(_NAV_TIMEOUT)
        # Google/YouTube consent in the EU: cookies that avoid the wall (best effort). With the persistent profile,
        # once a banner is accepted it is also saved → it stops appearing on subsequent visits.
        try:
            await _context.add_cookies([
                {"name": "SOCS", "value": "CAI", "domain": ".youtube.com", "path": "/"},
                {"name": "SOCS", "value": "CAI", "domain": ".google.com", "path": "/"},
                {"name": "CONSENT", "value": "YES+", "domain": ".youtube.com", "path": "/"},
                {"name": "CONSENT", "value": "YES+", "domain": ".google.com", "path": "/"},
                # Wallapop: OptanonConsent (OneTrust) + its own EU consent cookie
                {"name": "OptanonConsent",
                 "value": "isGpcEnabled=0&datestamp=Tue+Jul+2026+12%3A00%3A00+GMT%2B0200&version=6.29.0&isIABGlobal=false&hosts=&consentId=&interactionCount=1&landingPath=NotLandingPage&groups=C0001%3A1%2CC0002%3A1%2CC0003%3A1%2CC0004%3A1%2CC0005%3A1",
                 "domain": ".wallapop.com", "path": "/"},
                {"name": "euconsent-v2",
                 "value": "CQ...",  # placeholder — auto-click is the real mechanism
                 "domain": ".wallapop.com", "path": "/"},
                # Wallapop: accepted-banner marker (covers its own system when OneTrust is absent)
                {"name": "wp_consent", "value": "1", "domain": ".wallapop.com", "path": "/"},
                {"name": "_consent", "value": "1", "domain": ".wallapop.com", "path": "/"},
                {"name": "user_consent", "value": "true", "domain": ".wallapop.com", "path": "/"},
                {"name": "cookie_consent", "value": "accepted", "domain": ".wallapop.com", "path": "/"},
            ])
        except Exception:
            pass
    # ONE tab: reuse the one the persistent context already brings instead of opening another → no extra tabs.
    _page = _context.pages[0] if _context.pages else await _context.new_page()
    _emit("launched", f"navegador {'headless' if _headless() else 'ventana real'} · perfil persistente")
    return _page


# ── utilities ────────────────────────────────────────────────────────────────────────────────────────────────
_YT_RE = re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([0-9A-Za-z_-]{11})")
_YT_ID_RE = re.compile(r'"videoId":"([0-9A-Za-z_-]{11})"')


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip()
    if not s or " " in s:
        return False
    if s.startswith(("http://", "https://")):
        return True
    return bool(re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/.*)?$", s, re.I))   # domain with TLD


def _normalize_url(s: str) -> str:
    s = (s or "").strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def _youtube_id(s: str) -> str:
    m = _YT_RE.search(s or "")
    return m.group(1) if m else ""


def _draw_cursor(path: str, x: float, y: float) -> None:
    """Draw a mouse cursor (OS-style arrow) over the screenshot, at the VIRTUAL mouse position, so the operator can
    SEE where the automator is acting (the mouse lives inside server-side Chromium, invisible in the photo; this makes
    it visible). Best-effort: if Pillow fails, leave the screenshot as-is."""
    try:
        from PIL import Image, ImageDraw
        img = Image.open(path).convert("RGBA")
        ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        x, y = int(x), int(y)
        arrow = [(x, y), (x, y + 18), (x + 5, y + 13), (x + 9, y + 20),
                 (x + 12, y + 18), (x + 8, y + 12), (x + 14, y + 12)]
        d.polygon(arrow, fill=(250, 250, 250, 255))     # light fill
        d.line(arrow + [arrow[0]], fill=(20, 20, 20, 255), width=2, joint="curve")   # dark outline (visible on any background)
        d.ellipse([x - 6, y - 6, x + 6, y + 6], outline=(255, 70, 70, 230), width=2)  # halo to draw the eye
        img.alpha_composite(ov)
        img.convert("RGB").save(path)
    except Exception:
        pass


async def _capture() -> None:
    """Screenshot the viewport → widgets/_data/navegador/shot.png and bump rev (client <img> cache-bust)."""
    global _rev
    page = _page
    shot = f"{store.data_dir(WID)}/shot.png"
    await page.screenshot(path=shot, type="png", full_page=False)
    if _automating:                                     # running task → draw the virtual cursor where it is acting
        # OFF-LOOP (V2-035): the PIL composite is synchronous CPU work that held the GIL in the uvicorn loop and
        # starved the TTS audio pump (choppy voice). Move it to a thread → it does not block voice.
        await asyncio.to_thread(_draw_cursor, shot, _mouse["x"], _mouse["y"])
    _rev += 1
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    _write(mode="page", url=page.url, title=title or page.url, rev=_rev, loading=False, error="",
           youtube_id="", youtube_title="")
    _emit("screenshot", page.url, rev=_rev)


async def _goto(url: str, push: bool = True) -> None:
    global _idx, _hist
    page = await _ensure_page()
    _write(loading=True, error="", url=url)
    _emit("navigate", url)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await _dismiss_overlays(page)                    # close cookie banners that block the website
        await asyncio.sleep(0.35)                     # let the above-the-fold render before the screenshot
    except Exception as e:
        _write(loading=False, error=f"No pude abrir la página: {str(e).splitlines()[0][:200]}")
        _emit("nav_error", url, error=str(e)[:200])
        return
    if push:
        _hist = _hist[:_idx + 1] + [page.url]
        _idx = len(_hist) - 1
    await _capture()


# ── mailbox commands ────────────────────────────────────────────────────────────────────────────────────────
async def handle(action: str, payload: dict) -> None:
    payload = payload or {}
    if action == "open":
        raw = str(payload.get("url") or "").strip()
        if not raw:
            return
        yid = _youtube_id(raw)
        if yid:
            await _show_youtube(yid, "")
        elif _looks_like_url(raw):
            await _goto(_normalize_url(raw))
        else:
            await _search(raw)                        # loose text in the bar → web search
    elif action == "search":
        await _search(str(payload.get("q") or payload.get("url") or "").strip())
    elif action == "youtube":
        await _youtube(str(payload.get("q") or "").strip(), str(payload.get("url") or "").strip())
    elif action in ("back", "forward"):
        await _step(action)
    elif action == "reload":
        page = await _ensure_page()
        _write(loading=True)
        try:
            await page.reload(wait_until="domcontentloaded")
            await _dismiss_overlays(page)
            await asyncio.sleep(0.3)
        except Exception:
            pass
        await _capture()
    elif action == "scroll":
        await _scroll(float(payload.get("dy") or 0))
    elif action == "click":
        await _click(float(payload.get("x") or 0), float(payload.get("y") or 0))
    elif action == "type":
        await _type(str(payload.get("text") or ""))
    elif action == "press":
        await _press(str(payload.get("key") or ""))
    elif action in ("close", "quit", "close_browser"):
        await _close_browser()
    elif action == "automate":
        # SPAWN (no await): the owner's mailbox is SERIAL — if we waited for the whole loop, tasks would not run in
        # PARALLEL. Launch the task in the background and free the mailbox for the next command → N concurrent tasks,
        # each in its own tab. Keep the ref so GC does not collect it.
        _t = asyncio.create_task(_automate(str(payload.get("goal") or payload.get("task") or ""),
                                           str(payload.get("plan") or ""), str(payload.get("task_id") or "")))
        _running.add(_t)
        _t.add_done_callback(_running.discard)
    elif action == "browse":
        # SIMPLE navigation for a task/tab (no loop): open/search/youtube in ITS tab → vertical card.
        _t = asyncio.create_task(_browse(str(payload.get("task_id") or ""), str(payload.get("mode") or "open"),
                                         str(payload.get("url") or ""), str(payload.get("q") or "")))
        _running.add(_t)
        _t.add_done_callback(_running.discard)
    elif action == "authenticate":
        await _authenticate(str(payload.get("task_id") or ""), str(payload.get("url") or ""))
    elif action == "auth_done":
        await _auth_done(str(payload.get("task_id") or ""))
    elif action == "cancel_task":
        await _close_task(str(payload.get("task_id") or ""))
    elif action == "answer_task":
        from . import tasks
        tasks.answer(str(payload.get("task_id") or ""), str(payload.get("text") or ""))
    else:
        logger.debug(f"navegador: orden desconocida {action!r}")


_task_browsers: dict = {}   # task_id -> TaskBrowser (to close the tab when closing/canceling the card)
_running: set = set()       # in-flight asyncio tasks (prevents GC from collecting them)
_shot_lock = asyncio.Lock()  # serialize bring_to_front+capture across parallel tasks (headed paints one tab at a time)

# AUTHENTICATION — control state (one window → one login at a time; resume after auth_done).
_LOGIN_TIMEOUT = float(os.environ.get("NAVEGADOR_LOGIN_TIMEOUT", "600"))  # 10 min unfinished → reminder (does not kill)
_LOGIN_POLL = float(os.environ.get("NAVEGADOR_LOGIN_POLL", "2.5"))        # how often to watch the login window
_auth_resume: dict = {}     # task_id -> {"goal","plan","site"} for tasks to RESUME after login (requester + paused tasks)
_auth_active: str = ""      # site of the login IN PROGRESS ("" = none) — serializes: never open two login windows
_login_timeouts: dict = {}  # task_id -> asyncio.Task for the login watcher/poller (auto-detection + timeout)
_auth_baseline_cookies: dict = {}  # task_id -> set((domain,name)) when login opens → detect NEW cookies = session present

# Reaching login is DIFFERENT on every site → VERSATILE approach: (1) known login URL for common sites; (2) if none
# exists or it misses, open the domain and SEARCH the page for the "sign in" link/button (by text, multi-language)
# while AVOIDING registration, then click it. Never intentionally lands on the SIGN-UP page.
_LOGIN_URLS = {
    "google.com": "https://accounts.google.com/signin",
    "gmail.com": "https://accounts.google.com/signin/v2/identifier?service=mail",
    "youtube.com": "https://accounts.google.com/signin",
    "wallapop.com": "https://es.wallapop.com/login",
    "linkedin.com": "https://www.linkedin.com/login",
    "amazon.es": "https://www.amazon.es/ap/signin",
    "amazon.com": "https://www.amazon.com/ap/signin",
    "github.com": "https://github.com/login",
    "x.com": "https://x.com/i/flow/login",
    "twitter.com": "https://x.com/i/flow/login",
    "instagram.com": "https://www.instagram.com/accounts/login/",
    "facebook.com": "https://www.facebook.com/login",
    "outlook.com": "https://login.live.com/",
    "microsoft.com": "https://login.microsoftonline.com/",
}
_LOGIN_TEXT_RE = re.compile(r"(iniciar sesi[oó]n|inicia sesi[oó]n|log ?in|log ?on|sign ?in|acceder|entrar|mi cuenta)", re.I)
_REGISTER_TEXT_RE = re.compile(r"(regist|reg[ií]strate|sign ?up|crear cuenta|cr[eé]ate|new account|\b[úu]nete\b|join now)", re.I)


async def _automate(goal: str, plan: str = "", task_id: str = "") -> None:
    """Run the HYBRID DOM+vision loop (agent.py) for ONE task, in ITS OWN tab (TaskBrowser). Progress goes to the
    task feed (tasks.add_event via TaskBrowser._emit) and its card refreshes itself; when it finishes, results +
    proactive notice (voice+UI). The tab stays OPEN so the operator can see it; it closes when the card is closed.
    `plan` = Hermes high-level guide (best-effort)."""
    if not goal:
        return
    from . import agent, tasks
    if not task_id:
        task_id = tasks.create(goal)
    tasks.set_status(task_id, "working")
    tasks.set_phase(task_id, "buscando resultados", True)     # PHASE (spinner): the operator sees the PROCESS, not clicks
    tb = TaskBrowser(task_id)
    _task_browsers[task_id] = tb
    # ROBUSTNESS (V2-035): if the plan includes an already FILTERED results URL (first line `URL: …`, composed by the
    # planner from refined keywords + price), start the browser DIRECTLY on the results grid instead of typing into the
    # search box and navigating manually (the fragile path that got stuck on Wallapop). The rest of the plan remains
    # the loop guide.
    start_url = ""
    if plan:
        _m = re.match(r"\s*URL:\s*(\S+)", plan, re.I)
        if _m:
            start_url = _m.group(1).strip()
            plan = plan[_m.end():].lstrip("\n ")
    if start_url:
        try:
            tasks.milestone(task_id, f"➡️ voy directo a la rejilla de resultados filtrada")
            await tb.agent_act("navigate", {"url": start_url})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"navegador: navigate inicial a resultados falló: {e}")
    try:
        res = await agent.run_task(goal, tb, plan=plan)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "summary": f"error del automatizador: {str(e).splitlines()[0][:160]}"}
    # LOGIN WALL: the loop hit a sign-in page and did NOT type credentials. Open the real window so the operator can
    # sign in manually; the task is NOT closed — it remains paused and resumes by itself after auth_done.
    if res.get("needs_login"):
        await _begin_login(task_id, res.get("site", ""), res.get("login_url", ""), goal, plan)
        return
    summary = str(res.get("summary") or "")
    ok, success = bool(res.get("ok")), bool(res.get("success"))
    results = res.get("results")
    # RICH RESULTS: scrape listings from the final page + cheap model picks the best ones + conclusion.
    # Visible phases: collecting → (N listings) → investigating the best. Best-effort.
    if not results and ok:
        try:
            tasks.set_phase(task_id, "recopilando anuncios", True)
            items = await tb.extract_listings()
            if items:
                # OBSERVABILITY (V2-035): leave WHICH candidates were extracted in the feed (so we can later review
                # whether the search returned the requested thing —e.g. enduro— or the wrong category), not just
                # "N listings".
                _sample = "; ".join(
                    f"{(it.get('title') or '')[:40]}{(' · '+it.get('price')) if it.get('price') else ''}"
                    for it in items[:6])
                tasks.milestone(task_id, f"📋 {len(items)} anuncios encontrados: {_sample}")
                # EVIDENCE (2026-08-10): the milestone carries a readable sample, but AUDITING needs the source —
                # each candidate URL, which allows revisiting and checking whether the price and description were what
                # it claimed. Budgeted (`observability.evidence`), best-effort.
                try:
                    from observability import evidence as _evd
                    from voice.observer import emit as _emit_obs
                    _ev = _evd.web_results([{"title": it.get("title"), "url": it.get("url"),
                                             "snippet": it.get("price")} for it in items])
                    _emit_obs("navegador", "📋 candidatos extraídos", text=f"{len(items)} de {tb.page.url}",
                              extra={"id": "navegador", "task": task_id, "span": f"web:{task_id}",
                                     "trace": tasks.trace_of(task_id), "evidence": _ev})
                except Exception:
                    pass
                tasks.set_phase(task_id, "investigando los mejores", True)
                results = await agent.summarize_results(goal, items)
                if results and results.get("discarded"):
                    # OBSERVABILITY (V2-035): what was DISCARDED and WHY (e.g. "trial motorcycle — not enduro"), so
                    # the relevance filter can be reviewed.
                    _dis = "; ".join(f"{d.get('title', '')[:32]} ({d.get('reason', '')[:40]})"
                                     for d in results["discarded"][:5])
                    tasks.milestone(task_id, f"🚫 descartados {len(results['discarded'])} por no encajar: {_dis}")
                if results and results.get("items"):
                    _sel = "; ".join((it.get("title") or "")[:40] for it in results["items"][:5])
                    tasks.milestone(task_id, f"⭐ seleccionados {len(results['items'])}: {_sel}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"extracción de resultados falló: {e}")
    # SUCCESS by RESULT, not by what the model reports: if we got ranked listings, the task DID complete (the loop
    # sometimes closes with empty done {} → success False even though it reached the grid). Fix for saying "could not
    # fully complete" despite having results.
    if results and results.get("items"):
        success = True
        if not summary:
            summary = results.get("conclusion") or f"{len(results['items'])} resultados"
    if results:
        tasks.set_results(task_id, results)
    tasks.set_phase(task_id, "listo" if (ok and success) else ("terminado" if ok else "no pude completarlo"), False)
    tasks.finish(task_id, "done" if (ok and success) else ("done" if ok else "failed"),
                 ("✅ " if (ok and success) else "") + (summary or "sin resumen"))
    try:
        from voice import brain_notes
        head = "completé" if (ok and success) else "no pude completar del todo"
        brain_notes.push(f"[SISTEMA] Navegador (tarea {task_id}): {head} «{goal}». {summary} Está en su tarjeta "
                         f"'{tasks.inst_id(task_id)}'.")
    except Exception:
        pass
    try:
        from voice import proactive
        # The proactive notification is SPOKEN AS-IS (it does not go through FlashBrain for polishing): it must NEVER
        # leak the task's INTERNAL phrasing (`{goal}` comes in engineering third person, "Alex wants to search for
        # houses...") — it used to say "I tried with «Alex wants to search...»: ...", exposing internals (judge finding,
        # browser convo). User-facing message = summary only (already user-facing); raw objective stays in the
        # [SYSTEM] note (brain context), not in voice.
        tail_ = (summary or "").strip()
        if (ok and success):
            msg = f"Listo. {tail_}" if tail_ and tail_ != "sin resumen" else "Listo, lo tienes en su tarjeta."
        else:
            msg = (f"No pude terminarla del todo. {tail_}" if tail_ and tail_ != "sin resumen"
                   else "No pude terminarla del todo; lo dejé en su tarjeta por si quieres verlo.")
        await proactive.notify("navegador", msg, kind="notify")
    except Exception:
        pass


async def _browse(task_id: str, mode: str, url: str, q: str) -> None:
    """Simple navigation for one task/tab (browse, no automation loop) → its vertical card shows the screenshot + bar.
    Reuses TaskBrowser (one tab per task, same window). Does not raise."""
    if not task_id:
        return
    from . import tasks
    tb = _task_browsers.get(task_id) or TaskBrowser(task_id)
    _task_browsers[task_id] = tb
    tasks.set_status(task_id, "working")
    tasks.set_phase(task_id, "abriendo", True)
    try:
        if mode == "search":
            await tb.search(q or url)
        elif mode == "youtube":
            await tb.open_youtube(q, url)
        else:
            await tb.open_target(url or q)
    except Exception as e:  # noqa: BLE001
        tasks.milestone(task_id, f"⚠️ {str(e).splitlines()[0][:120]}")
    tasks.set_status(task_id, "open")
    tasks.set_phase(task_id, "abierto", False)


def _login_url_for(site: str) -> str | None:
    """KNOWN login URL for `site` (domain), or None. Matches by base domain (sub.domain.tld → domain.tld)."""
    host = (site or "").strip().lower()
    host = host.replace("https://", "").replace("http://", "").split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    for key, u in _LOGIN_URLS.items():
        if host == key or host.endswith("." + key):
            return u
    return None


async def _click_login_affordance(page) -> bool:
    """VERSATILE: search the page for the link/button that leads to LOGIN (by text, multi-language) while AVOIDING
    registration, and click it. Returns True if it clicked something. This reaches login even without its exact URL."""
    try:
        cands = await page.query_selector_all("a, button, [role=button]")
    except Exception:
        return False
    best = None
    for el in cands[:400]:
        try:
            txt = ((await el.inner_text()) or "").strip()
            blob = f"{txt} {(await el.get_attribute('aria-label')) or ''} {(await el.get_attribute('href')) or ''}"
        except Exception:
            continue
        if not blob.strip() or not _LOGIN_TEXT_RE.search(blob):
            continue
        # registration affordance (and its own text does not say login) → skip it, never land on registration
        if _REGISTER_TEXT_RE.search(blob) and not _LOGIN_TEXT_RE.search(txt):
            continue
        best = el
        if _LOGIN_TEXT_RE.search(txt):                # prioritize the element whose own text says "sign in"
            break
    if best is None:
        return False
    try:
        await best.click(timeout=4000)
        await page.wait_for_load_state("domcontentloaded", timeout=6000)
        return True
    except Exception:
        return False


async def _reach_login(tb, site: str) -> None:
    """Take the tab to the LOGIN page for `site`, VERSATILE (every site is different) and NEVER to registration:
    (1) known login URL; (2) if it misses, open the domain and click the sign-in link/button."""
    from . import agent
    known = _login_url_for(site)
    target = known or (site if site.startswith("http") else f"https://{site.strip('/')}")
    try:
        await tb.open_target(target)
    except Exception:
        pass
    if tb.page is None:
        return
    await _dismiss_overlays(tb.page)
    try:
        state = await tb.snapshot_for_agent()
    except Exception:
        state = {"url": tb.page.url, "elements": ""}
    if agent._looks_like_login(state.get("url", ""), state.get("elements", "")):
        return                                        # the known URL already left us on login
    await _click_login_affordance(tb.page)            # versatile: find and click "sign in"
    await _dismiss_overlays(tb.page)


async def _cookie_fingerprint(tb) -> set:
    """Fingerprint (domain,name) of current profile cookies — used to detect NEW cookies after login."""
    try:
        cookies = await tb.page.context.cookies()
        return {(c.get("domain", ""), c.get("name", "")) for c in cookies}
    except Exception:
        return set()


async def _authenticate(task_id: str, url: str, *, site: str = "", goal: str = "", plan: str = "") -> None:
    """Open the REAL WINDOW (visible) directly on the site's LOGIN and WATCH it: once it detects the session is
    established (left login/registration + new cookies appeared), it closes by itself and returns to headless —
    ZERO manual steps. The session is saved in the PERSISTENT profile (no need to copy cookies from system Chrome).
    `url` = already detected login URL (need_login path) or the site/domain to resolve (authenticate_web)."""
    global _visible_override, _auth_active
    from . import agent, auth_memory, tasks
    url = (url or "wallapop.com").strip()
    site = (site or _login_site_of(url)).strip().lower()
    if not task_id:
        task_id = tasks.create(f"Iniciar sesión · {site or url}", title=f"Login · {site or url}")
    _auth_resume.setdefault(task_id, {"goal": goal, "plan": plan, "site": site})
    # GUARD: is there ALREADY a session? Then do NOT open any login — confirm it and continue the task (bug: it
    # reopened Wallapop login while already authenticated). Headless check, no window.
    if await _already_authenticated(site):
        auth_memory.record_session_established(site)
        # search objective to resume: the task's objective, or the one left in the memory checkpoint (auth_pendiente).
        pend = auth_memory.read_auth_pending() or {}
        goal_to_run = ((_auth_resume.get(task_id) or {}).get("goal") or goal or pend.get("objetivo") or "").strip()
        auth_memory.clear_auth_pending()
        tasks.set_login_wait(task_id, False)
        tasks.milestone(task_id, f"✅ Ya había sesión en «{site}» — no hace falta iniciar sesión")
        try:
            from voice import proactive
            await proactive.notify("navegador", f"Ya estabas dentro de {site}, no hace falta iniciar sesión. Sigo.",
                                   kind="notify")
        except Exception:
            pass
        if goal_to_run:                                          # search to resume → launch it now (authenticated)
            tasks.set_phase(task_id, "retomando la búsqueda", True)
            _auth_resume.pop(task_id, None)
            _t = asyncio.create_task(_automate(goal_to_run, "", task_id))
            _running.add(_t)
            _t.add_done_callback(_running.discard)
        else:                                                     # no objective (standalone login) → close the card, not left hanging
            tasks.set_phase(task_id, "ya tenías sesión", False)
            tasks.finish(task_id, "done", "Ya tenías sesión iniciada.")
        await _resume_paused_tasks()                              # resume OTHER tasks paused by login (if any)
        return
    if _in_container():
        # 2026-08-03: in a headless container (cloud) there is no display → the "headed" relaunch below ALWAYS
        # silently degrades to headless (`_ensure_page`), and the task waits for a login that can never happen —
        # previously this looped forever (voice AND widget hung, observed live with Wallapop). Stop here, BEFORE
        # trying, with a clear message instead of a phantom attempt.
        msg = (f"Para entrar en {site or url} hace falta iniciar sesión, y eso todavía no lo puedo hacer desde la "
               "nube — necesitaría abrir una ventana de navegador que aquí no existe. Instala la versión local "
               "(desde GitHub) si quieres usar sitios que exigen iniciar sesión.")
        await _fail_paused_tasks(msg)
        try:
            from voice import proactive
            await proactive.notify("navegador", msg, speak=True)
        except Exception:
            pass
        return
    _auth_active = site
    auth_memory.checkpoint_auth_pending(site, task_id, goal)       # durable breadcrumb (survives crash/restart)
    _visible_override = True                                       # force VISIBLE for login
    await stop()                                                  # relaunch headed (profile/cookies persist)
    _task_browsers.pop(task_id, None)
    tb = TaskBrowser(task_id)
    _task_browsers[task_id] = tb
    tasks.set_status(task_id, "needs_input")
    tasks.set_phase(task_id, "esperando tu inicio de sesión", True)
    tasks.set_login_wait(task_id, True)
    try:
        if agent._LOGIN_URL_RE.search(url.lower()):               # already IS a login URL (need_login path) → open it
            await tb.open_target(url)
            if tb.page is not None:
                await _dismiss_overlays(tb.page)
        else:                                                     # site/domain → RESOLVE login (versatile)
            await _reach_login(tb, site or url)
    except Exception as e:  # noqa: BLE001
        tasks.milestone(task_id, f"⚠️ {str(e).splitlines()[0][:100]}")
    _auth_baseline_cookies[task_id] = await _cookie_fingerprint(tb)
    tasks.milestone(task_id, "🔓 Inicia sesión en la ventana; lo detecto solo cuando entres — no tienes que hacer nada más")
    try:
        from voice import proactive
        await proactive.notify("navegador", "Te abrí el login. Entra con tu cuenta; en cuanto vea que estás dentro, "
                               "sigo yo solo.", speak=True)
    except Exception:
        pass
    _arm_login_watch(task_id, site)                               # WATCH the window → auto-detect login


async def _begin_login(task_id: str, site: str, login_url: str, goal: str = "", plan: str = "") -> None:
    """A login wall stopped a task. PAUSE the other active tasks (one window → headed relaunch kills their tabs), record
    them for resumption, and open the login window (which watches itself). They resume in auth_done."""
    from . import tasks
    site = (site or _login_site_of(login_url)).strip().lower()
    _auth_resume[task_id] = {"goal": goal, "plan": plan, "site": site}
    for other in list(tasks.active_ids()):
        if other == task_id:
            continue
        ot = tasks.get(other)
        if ot.get("goal"):
            _auth_resume.setdefault(other, {"goal": ot["goal"], "plan": "", "site": site})
        tasks.set_status(other, "needs_input")
        tasks.milestone(other, "⏸ en pausa mientras inicias sesión; la reanudo al terminar")
    await _authenticate(task_id, login_url, site=site, goal=goal, plan=plan)


def _arm_login_watch(task_id: str, site: str) -> None:
    """(Re)arm the POLLER that watches the login window (auto-detection + soft timeout)."""
    old = _login_timeouts.pop(task_id, None)
    if old:
        old.cancel()
    t = asyncio.create_task(_login_watch(task_id, site))
    _login_timeouts[task_id] = t
    _running.add(t)
    t.add_done_callback(_running.discard)


async def _is_logged_in(task_id: str, tb, site: str) -> bool:
    """Is the session established? VERSATILE signal (without guessing per-site cookie names): the page is NO LONGER a
    login/registration page AND NEW cookies appeared compared with the moment login opened (navigating login by itself
    does not create a session; signing in does leave cookies and redirects away from the form)."""
    from . import agent
    try:
        state = await tb.snapshot_for_agent()
    except Exception:
        return False
    url = state.get("url", "")
    if agent._looks_like_login(url, state.get("elements", "")) or _REGISTER_TEXT_RE.search(url):
        return False                                              # still on login/registration
    new_cookies = await _cookie_fingerprint(tb) - _auth_baseline_cookies.get(task_id, set())
    return len(new_cookies) >= 1


async def _login_watch(task_id: str, site: str) -> None:
    """WATCH the login window: every `_LOGIN_POLL`s, capture the page (the card shows it live) and check whether the
    session is established; 2 consecutive positive reads trigger `_auth_done` ALONE (zero manual steps).
    `_LOGIN_TIMEOUT` unfinished → soft reminder, no kill. The button/voice remain as a safety net."""
    from . import tasks
    stable = 0
    waited = 0.0
    reminded = False
    try:
        while True:
            await asyncio.sleep(_LOGIN_POLL)
            waited += _LOGIN_POLL
            t = tasks.get(task_id)
            if not t or not t.get("awaiting_login"):
                return                                            # resolved another way (button/voice/cancel)
            tb = _task_browsers.get(task_id)
            if tb is None:
                return
            try:
                await tb._capture()                               # refresh the live capture in the card
            except Exception:
                pass
            stable = stable + 1 if await _is_logged_in(task_id, tb, site) else 0
            if stable >= 2:                                       # confirmed in 2 reads → close by itself
                tasks.milestone(task_id, "✅ Detecté que ya iniciaste sesión")
                await _auth_done(task_id)
                return
            if not reminded and waited >= _LOGIN_TIMEOUT:
                reminded = True
                tasks.milestone(task_id, "⏰ Sigo vigilando la ventana de login; tómate tu tiempo.")
                try:
                    from voice import proactive
                    await proactive.notify("navegador", f"Sigo pendiente de tu login en {site}, sin prisa.",
                                           kind="notify")
                except Exception:
                    pass
    except asyncio.CancelledError:
        return


async def _auth_done(task_id: str) -> None:
    """The operator finished signing in → return to HEADLESS; the session remains in the persistent profile (cookies on
    disk). PROBE that the session really stuck; if so, record the ESTABLISHED breadcrumb in memory, clear the
    half-finished checkpoint, and RESUME (automatically) the paused tasks. Close the visible window (clean desktop)."""
    global _visible_override, _auth_active
    from . import auth_memory, tasks
    w = _login_timeouts.pop(task_id, None)
    if w and w is not asyncio.current_task():
        w.cancel()                                    # stop the poller (unless it is the caller)
    _auth_baseline_cookies.pop(task_id, None)
    _visible_override = False                         # return to headless
    if task_id:
        tasks.set_login_wait(task_id, False)
        tasks.set_phase(task_id, "sesión guardada", False)
        tasks.milestone(task_id, "✅ Sesión guardada en el perfil")
        _task_browsers.pop(task_id, None)
    await stop()                                      # close the window; the profile (cookies) persists → relaunch headless
    site = _auth_active or (_auth_resume.get(task_id) or {}).get("site") or ""
    # POST-LOGIN PROBE: did the session stick or did we bounce back to login? (best-effort → if unsure assume OK, do not block).
    if site and not await _probe_logged_in(site):
        tasks.milestone(task_id, "⚠️ No detecté la sesión iniciada; puede que el login no se completara.")
        auth_memory.checkpoint_auth_pending(site, task_id, (_auth_resume.get(task_id) or {}).get("goal", ""))
        _auth_active = ""
        try:
            from voice import proactive
            await proactive.notify("navegador", f"No me quedó guardada la sesión de {site}. ¿Reintentamos el "
                                   f"inicio de sesión?", kind="notify")
        except Exception:
            pass
        return
    if site:
        auth_memory.record_session_established(site)  # recallable ESTABLISHED marker (the secret stays only in the profile)
    auth_memory.clear_auth_pending()
    _auth_active = ""
    await _resume_paused_tasks()
    try:
        from voice import proactive
        await proactive.notify("navegador", "Sesión guardada, sigo con lo tuyo.", kind="notify")
    except Exception:
        pass


async def _resume_paused_tasks() -> None:
    """Resume (re-enqueue `automate`) ALL tasks recorded when login started: the requester + paused tasks. Drains
    `_auth_resume`. Cancelled tasks or tasks without an objective are discarded."""
    from . import tasks
    items = list(_auth_resume.items())
    _auth_resume.clear()
    for tid, info in items:
        goal = (info or {}).get("goal", "")
        if not goal or tasks.is_cancelled(tid):
            continue
        tasks.set_status(tid, "queued")
        tasks.milestone(tid, "▶️ reanudo la tarea, ya autenticado")
        _t = asyncio.create_task(_automate(goal, (info or {}).get("plan", ""), tid))
        _running.add(_t)
        _t.add_done_callback(_running.discard)


def _in_container() -> bool:
    """Are we running in a headless container (cloud), without a display for a real window? Same accessor as
    `nucleo/workers/providers.py::_is_container()` — the local Claude Code license and the login window share the same
    limitation: neither exists inside a container."""
    try:
        from config import doctor
        return bool(doctor.hardware().get("container"))
    except Exception:
        return False


async def _fail_paused_tasks(message: str) -> None:
    """Cleanly close the task that requested login + tasks paused waiting for it — sibling of `_resume_paused_tasks`,
    for cases where login CANNOT be resolved in this environment (instead of leaving them hanging forever waiting for
    a login that will never happen)."""
    from . import tasks
    items = list(_auth_resume.items())
    _auth_resume.clear()
    for tid, _info in items:
        if tasks.is_cancelled(tid):
            continue
        tasks.set_login_wait(tid, False)
        tasks.finish(tid, "failed", message)


# Only STRONG login intent for detecting "sign-in required" (not ambiguous text like "my account"/"enter", which also
# appears WHILE logged in → false positives).
_LOGIN_STRICT_RE = re.compile(r"(iniciar sesi[oó]n|inicia sesi[oó]n|log ?in|sign ?in)", re.I)


async def _find_login_affordance(page) -> bool:
    """Is there a VISIBLE 'sign in' link/button on the page? Presence = NO session (the site invites you to enter);
    absence (on a page that is not login) = you are already in (it shows your account menu)."""
    try:
        cands = await page.query_selector_all("a, button, [role=button]")
    except Exception:
        return False
    for el in cands[:400]:
        try:
            txt = ((await el.inner_text()) or "").strip() or ((await el.get_attribute("aria-label")) or "")
        except Exception:
            continue
        if txt and _LOGIN_STRICT_RE.search(txt) and not _REGISTER_TEXT_RE.search(txt):
            try:
                if await el.is_visible():
                    return True
            except Exception:
                return True
    return False


async def _already_authenticated(site: str) -> bool:
    """Is there ALREADY a session on `site`? Navigate headless and verify that it is NOT a login screen AND there is
    NO visible 'sign in' button (the site already shows your account). Avoids reopening login when already inside
    (bug 2026-07-10: resumed the search and reopened Wallapop login while already authenticated). Best-effort: if in
    doubt return False (better to check login than act without an account)."""
    if not site:
        return False
    from . import agent
    try:
        page = await _ensure_page()
        url = site if site.startswith("http") else f"https://{site.strip('/')}"
        await page.goto(url, wait_until="domcontentloaded")
        await _dismiss_overlays(page)
        await asyncio.sleep(0.5)
        if agent._looks_like_login(page.url or "", ""):
            return False
        return not await _find_login_affordance(page)
    except Exception:
        return False


async def _probe_logged_in(site: str) -> bool:
    """Navigate to the site (headless) and verify it does NOT bounce to a login screen → the session stuck. Reuses the
    `agent._looks_like_login` detector. Best-effort: any failure → True (do not block on a doubtful probe)."""
    if not site:
        return True
    from . import agent
    try:
        page = await _ensure_page()
        url = site if site.startswith("http") else f"https://{site}"
        await page.goto(url, wait_until="domcontentloaded")
        await _dismiss_overlays(page)
        await asyncio.sleep(0.4)
        return not agent._looks_like_login(page.url or "", "")
    except Exception:
        return True


def _login_site_of(url: str) -> str:
    """Readable host (without www) from a login URL, used to name the site if the loop did not pass it."""
    try:
        from urllib.parse import urlsplit
        host = (urlsplit(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host or "el sitio"
    except Exception:
        return "el sitio"


async def _close_task(task_id: str) -> None:
    """Close a task tab and mark it cancelled (when closing its card or by operator command)."""
    from . import tasks
    tb = _task_browsers.pop(task_id, None)
    if tb:
        await tb.close()
    if not tasks.is_cancelled(task_id) and tasks.get(task_id).get("status") in ("queued", "working", "needs_input"):
        tasks.cancel(task_id)


async def _search(q: str) -> None:
    if not q:
        return
    await _goto(_SEARCH_URL.replace("{q}", quote_plus(q)))


async def _step(direction: str) -> None:
    global _idx
    page = await _ensure_page()
    _write(loading=True)
    try:
        if direction == "back":
            await page.go_back(wait_until="domcontentloaded")
            _idx = max(0, _idx - 1)
        else:
            await page.go_forward(wait_until="domcontentloaded")
            _idx = min(len(_hist) - 1, _idx + 1)
        await asyncio.sleep(0.3)
    except Exception:
        pass
    await _capture()


async def _scroll(dy: float) -> None:
    page = await _ensure_page()
    try:
        await page.mouse.wheel(0, dy)
        await asyncio.sleep(0.2)
    except Exception:
        pass
    await _capture()


async def _click(x: float, y: float) -> None:
    global _idx, _hist
    page = await _ensure_page()
    _write(loading=True)
    _emit("click", f"{int(x)},{int(y)}")
    try:
        await page.mouse.click(x, y)
        await asyncio.sleep(0.6)                       # let a navigating click settle
    except Exception as e:
        _write(loading=False, error=f"No pude hacer clic: {str(e).splitlines()[0][:160]}")
        return
    if page.url and (not _hist or page.url != _hist[_idx if 0 <= _idx < len(_hist) else -1]):
        _hist = _hist[:_idx + 1] + [page.url]          # a click that navigated pushes to history
        _idx = len(_hist) - 1
    await _capture()


async def _type(text: str) -> None:
    page = await _ensure_page()
    try:
        await page.keyboard.type(text, delay=15)
    except Exception:
        pass
    await _capture()


async def _press(key: str) -> None:
    page = await _ensure_page()
    _write(loading=True)
    try:
        await page.keyboard.press(key or "Enter")
        await asyncio.sleep(0.6)
    except Exception:
        pass
    await _capture()


# ── YouTube (embedded player, not screenshot) ────────────────────────────────────────────────────────────────
async def _youtube(q: str, url: str) -> None:
    yid = _youtube_id(url) or (url if re.fullmatch(r"[0-9A-Za-z_-]{11}", url or "") else "")
    if yid:
        await _show_youtube(yid, "")
        return
    if not q:
        return
    # Resolve the first search video with Chromium (no API key): scrape "videoId" from the results HTML.
    page = await _ensure_page()
    _write(loading=True, error="")
    _emit("yt_search", q)
    try:
        await page.goto(f"https://www.youtube.com/results?search_query={quote_plus(q)}",
                        wait_until="domcontentloaded")
        await _dismiss_overlays(page)
        await asyncio.sleep(0.5)
        html = await page.content()
    except Exception as e:
        _write(loading=False, error=f"No pude buscar en YouTube: {str(e)[:160]}")
        return
    m = _YT_ID_RE.search(html)
    if m:
        await _show_youtube(m.group(1), q)
    else:
        await _capture()                               # no id → at least show the results as a page


async def _show_youtube(video_id: str, title: str) -> None:
    global _idx, _hist
    url = f"https://www.youtube.com/watch?v={video_id}"
    _hist = _hist[:_idx + 1] + [url]
    _idx = len(_hist) - 1
    _write(mode="youtube", url=url, title=title or "YouTube", youtube_id=video_id,
           youtube_title=title, loading=False, error="")
    _emit("youtube", video_id, title=title)


# DOM/accessibility snapshot + human-like input primitives moved to dom.py (2026-08-17 modularization
# pass) — page-parametric, no module-global coupling. Re-exported here since TaskBrowser's own methods
# below reference these as bare names.
from widgets.navegador.dom import (  # noqa: F401 — re-export
    _DANGER_RE, _INTERACTIVE, _JS_EXTRACT, _describe_el, _JS_DESCRIBE, _bulk_metas, _snapshot_lines,
    _human_move, _human_click_handle, _human_type_handle, _human_click_at,
)


# ── TaskBrowser: ONE TAB dedicated to a task ─────────────────────────────────────────────────────────────────
# Encapsulates its page + mouse + refs and exposes the SAME interface that agent.py expects from `owner`
# (snapshot_for_agent / agent_act / screenshot_b64 / _emit), so it can drive ITS tab without touching the main tab
# state (browse_web). 1:1 mapping: task ↔ tab ↔ canvas card. All tabs live in the SAME window (shared persistent
# context). Reuses page-parametric helpers (_human_*, _dismiss_overlays, _describe_el).
class TaskBrowser:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.page = None
        self.mouse = {"x": 0.0, "y": 0.0}   # this tab's OWN mouse
        self.refs: dict = {}
        self.rev = 0

    async def ensure(self):
        if self.page is not None and not self.page.is_closed():
            return self.page
        await _ensure_page()                 # ensure the window (persistent context) + main tab
        self.page = await _context.new_page()   # new TAB in the SAME window
        self._emit("tab_open", f"pestaña de la tarea {self.task_id}")
        return self.page

    def _emit(self, label: str, text: str = "", **extra) -> None:
        # Observer only (/debug). Clicks/navigation/captures do NOT go to the card feed: the feed tells the PROCESS
        # (phases + milestones), not every action. Milestones are pushed by the flow (_automate) with tasks.milestone.
        # V2-044: each navigation step is chained to the phrase that requested the task (the owner runs in the server
        # loop, without turn context → the trace lives in the task registry).
        if "trace" not in extra:
            try:
                from widgets.navegador import tasks as _tasks
                _tid = _tasks.trace_of(self.task_id)
                if _tid:
                    extra["trace"] = _tid
                    extra["span"] = f"web:{self.task_id}"
            except Exception:
                pass
        _emit(label, text, task=self.task_id, **extra)

    async def _capture(self) -> None:
        page = self.page
        shot = f"{store.data_dir(WID)}/shot-{self.task_id}.png"
        async with _shot_lock:               # serialize captures across parallel tasks
            # NO bring_to_front: in headless (default) all tabs render; bringing it to front also stole the operator's
            # focus/cursor (they could not type on their computer). Playwright screenshots background tabs.
            await page.screenshot(path=shot, type="png", full_page=False)
        # OFF-LOOP (V2-035): move PIL cursor compositing to a thread → does not steal GIL from the TTS audio pump.
        await asyncio.to_thread(_draw_cursor, shot, self.mouse["x"], self.mouse["y"])
        self.rev += 1
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        from . import tasks
        tasks.update_view(self.task_id, url=page.url, page_title=title or page.url, shot_rev=self.rev)
        self._emit("screenshot", page.url)

    async def _goto(self, url: str) -> None:
        page = await self.ensure()
        self._emit("navigate", url)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await _dismiss_overlays(page)
            await asyncio.sleep(0.35)
        except Exception as e:
            self._emit("nav_error", str(e).splitlines()[0][:160])
            return
        await self._capture()

    async def _reap_popups(self) -> None:
        """TASK 3 — avoid accumulating tabs: close popups (target=_blank) that the website opens after clicking (seen:
        30 tabs in one study). If the popup was the listing we meant to view, ABSORB its URL into OUR tab and close it
        → one listing = same tab, processed and discarded. Never touches another task's tab."""
        try:
            ctx = self.page.context
        except Exception:
            return
        owned = {tb.page for tb in _task_browsers.values() if getattr(tb, "page", None)}
        absorb = ""
        for p in list(ctx.pages):
            if p is self.page or p in owned:
                continue
            try:
                if p.url and p.url != "about:blank" and not absorb:
                    absorb = p.url
                await p.close()
            except Exception:
                pass
        if absorb and absorb != self.page.url:
            try:
                await self.page.goto(absorb, wait_until="domcontentloaded")
                await _dismiss_overlays(self.page)
                await asyncio.sleep(0.3)
            except Exception:
                pass

    async def open_target(self, raw: str) -> None:
        """Simple navigation (browse, no loop): open a URL/domain, or search if it is loose text, or YouTube."""
        raw = (raw or "").strip()
        if not raw:
            return
        yid = _youtube_id(raw)
        if yid:
            await self._goto(f"https://www.youtube.com/watch?v={yid}")
        elif _looks_like_url(raw):
            await self._goto(_normalize_url(raw))
        else:
            await self.search(raw)

    async def search(self, q: str) -> None:
        q = (q or "").strip()
        if q:
            await self._goto(_SEARCH_URL.replace("{q}", quote_plus(q)))

    async def open_youtube(self, q: str, url: str = "") -> None:
        yid = _youtube_id(url) or (url if re.fullmatch(r"[0-9A-Za-z_-]{11}", url or "") else "")
        if not yid and q:
            page = await self.ensure()
            try:
                await page.goto(f"https://www.youtube.com/results?search_query={quote_plus(q)}",
                                wait_until="domcontentloaded")
                await asyncio.sleep(0.5)
                m = _YT_ID_RE.search(await page.content())
                yid = m.group(1) if m else ""
            except Exception:
                pass
        await self._goto(f"https://www.youtube.com/watch?v={yid}" if yid
                         else f"https://www.youtube.com/results?search_query={quote_plus(q)}")

    async def snapshot_for_agent(self) -> dict:
        page = await self.ensure()
        await _dismiss_overlays(page)
        self.refs = {}
        try:
            handles = await page.query_selector_all(_INTERACTIVE)
        except Exception:
            handles = []
        metas = await _bulk_metas(page)          # ONE call (not ~7×N) → does not starve voice through the GIL (V2-036 fix #1)
        lines = _snapshot_lines(handles, metas, self.refs)
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        return {"url": page.url, "title": title or "", "elements": "\n".join(lines)}

    async def screenshot_b64(self) -> str:
        import base64
        page = await self.ensure()
        png = await page.screenshot(type="png", full_page=False)
        return base64.b64encode(png).decode()

    async def agent_act(self, action: str, args: dict) -> tuple[bool, str]:
        page = await self.ensure()
        try:
            if action == "navigate":
                await self._goto(_normalize_url(str(args.get("url", ""))))
                return True, f"navegado a {page.url}"
            if action == "scroll":
                try:
                    await page.mouse.wheel(0, float(args.get("dy", 600)))
                    await asyncio.sleep(0.2)
                except Exception:
                    pass
                await self._capture()
                return True, "desplazado"
            if action == "press":
                try:
                    await page.keyboard.press(str(args.get("key", "Enter")) or "Enter")
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                await self._capture()
                return True, "tecla pulsada"
            if action in ("click_at", "type_at"):
                x, y = float(args.get("x", 0)), float(args.get("y", 0))
                self._emit("vision_" + ("click" if action == "click_at" else "type"), f"{int(x)},{int(y)}")
                await _human_click_at(page, x, y, self.mouse)
                if action == "type_at":
                    await page.keyboard.type(str(args.get("text", "")), delay=random.randint(40, 120))
                    if bool(args.get("submit")):
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        await page.keyboard.press("Enter")
                await asyncio.sleep(0.7)
                await self._reap_popups()
                await self._capture()
                return True, ("clic" if action == "click_at" else "texto") + " (visión) hecho"
            ref = int(args.get("ref", 0))
            h = self.refs.get(ref)
            if h is None:
                return False, f"ref {ref} no existe en el snapshot actual"
            if action == "click":
                # CONFIRM-GATE (safety): if the button looks IRREVERSIBLE (buy/pay/publish/delete...), STOP and ask
                # the operator for OK BEFORE clicking. The automator never buys/publishes/deletes blindly.
                try:
                    _, _name = await _describe_el(h)
                except Exception:
                    _name = ""
                if _DANGER_RE.search((_name or "").lower()):
                    if not await self._confirm(_name):
                        return False, f"acción «{_name[:40]}» NO confirmada por el operador"
                await _human_click_handle(page, h, self.mouse)
                await asyncio.sleep(0.7)
                await self._reap_popups()                     # TASK 3: absorb/close popups → no accumulated tabs
                await self._capture()
                return True, "clic hecho"
            if action == "type":
                await _human_type_handle(page, h, str(args.get("text", "")), bool(args.get("submit")), self.mouse)
                await asyncio.sleep(0.6)
                await self._capture()
                return True, "texto escrito"
            if action == "select_option":
                # NATIVE <select>: cannot be filled with type/click_at (the native popup is not scrapeable).
                # Playwright `select_option` resolves it by LABEL (visible text), value, or index. Without this, a
                # required form dropdown (ITV cancellation reason, dates...) BLOCKS the worker → timeout.
                val = str(args.get("value") or args.get("text") or args.get("label") or "").strip()
                idx = args.get("index")
                try:
                    if idx is not None:
                        await h.select_option(index=int(idx))
                    else:
                        try:
                            await h.select_option(label=val)
                        except Exception:
                            await h.select_option(val)   # value or generic label (fallback)
                except Exception as e:  # noqa: BLE001
                    return False, f"no pude seleccionar «{val or idx}» en el desplegable: {str(e).splitlines()[0][:80]}"
                await asyncio.sleep(0.4)
                await self._capture()
                return True, f"opción «{val or idx}» seleccionada"
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e).splitlines()[0][:120]}"
        return False, f"acción desconocida: {action}"

    async def _confirm(self, label: str) -> bool:
        """Ask the operator for OK on an irreversible action and WAIT for the response (by voice, routed to this task).
        Returns True if approved. Timeout ~60s → do not execute (fail-safe). Cancellable."""
        from . import tasks
        tasks.ask(self.task_id, f"Voy a pulsar «{label[:50]}». ¿Lo confirmo? (dime sí o no)")
        try:
            from voice import proactive
            await proactive.notify("navegador", f"La tarea {self.task_id} necesita tu OK para pulsar "
                                   f"«{label[:40]}». ¿Confirmo?", kind="notify")
        except Exception:
            pass
        for _ in range(120):                              # ~60s
            if tasks.is_cancelled(self.task_id):
                return False
            ans = tasks.take_answer(self.task_id)
            if ans:
                aff = any(w in ans.lower() for w in
                          ("sí", "si", "ok", "vale", "dale", "confirm", "adelante", "hazlo", "yes", "claro"))
                tasks.set_status(self.task_id, "working")
                tasks.add_event(self.task_id, "✅ confirmado" if aff else "🚫 no confirmado")
                return aff
            await asyncio.sleep(0.5)
        tasks.set_status(self.task_id, "working")
        tasks.add_event(self.task_id, "⏱ sin confirmación → no ejecuto la acción")
        return False

    async def extract_listings(self, limit: int = 14) -> list:
        """Scrape the CURRENT page for 'listings'/results: links with image and/or price (generic — Wallapop,
        Idealista, stores). Returns [{title, price, url, image}]. Does not raise."""
        try:
            return await self.page.evaluate(_JS_EXTRACT, limit) or []
        except Exception:
            return []

    async def close(self) -> None:
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        self.page = None
