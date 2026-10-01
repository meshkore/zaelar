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
from . import click_gate as _click_gate
from nucleo.errors import brief as _brief


def _say():
    """The language table (V2-682) — this owner's three spoken sentences were f-strings at their own
    `notify` call, and an English operator was told about his own browser in Spanish."""
    from i18n import langs as _lg
    return _lg.current_language()


WID = "navegador"
VIEWPORT = {"width": 1280, "height": 800}
HOME = {"mode": "blank", "url": "", "title": "Nuevo navegador"}
_NAV_TIMEOUT = 15_000   # ms — goto cap; a slow website must not block the mailbox
#: Cap for a DOM READ after an action. The browser is a DIRECT connection: an action that works, works in
#: seconds — measured against the live lab on a real site, `navigate` 4.2 s, `look` 4.2 s, `extract` 0.05 s.
#: What is NOT bounded by anything is `page.evaluate`: Playwright gives it no timeout, so it waits for an
#: execution context, and a page NAVIGATING (the Enter after typing in a search box) has none until the new
#: document is ready. Measured 2026-08-24 on `search-buy-guitar__es`: the text WAS typed and the screenshot
#: WAS taken at 18:03:48, then silence until the CLI gave up at 18:05:15 — 90 s of a 250 s round spent on an
#: action that had already succeeded. Operator's rule, same day: «it must not have ninety-second timeouts
#: under any circumstances». Generous against the 4 s measured, brutal against the 90 that was there.
_DOM_TIMEOUT_S = 8.0

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


def _host_of(url: str) -> str:
    """The DOMAIN of a URL — the granularity at which cookie consent exists.

    It was stored by URL, and `type --submit` in a search engine CHANGES the URL: the following look would
    scan everything again. Measured in the 19:39 run on `search-buy-guitar__es`: `type` worked (at 19:39:07
    the capture was already `/search?keywords=guitarra+acustica`) and the bridge still reported a timeout at
    25 s, three times in a row. A CMP is per domain: accepted on wallapop.com, it does not reappear while
    moving within it.
    """
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower()
    except Exception:  # noqa: BLE001
        return ""


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
    #
    # ONE query per frame, not one PER SELECTOR. It used to be N frames × M selectors round-tripped, and a
    # results page with ad iframes has many frames: measured, the full sweep cost ~15-20 s in Wallapop search.
    # The selectors are combined into one —which is what step (1) immediately above already does— so the
    # browser resolves the list in one go.
    _combined = ", ".join(_COOKIE_SELECTORS)
    for fr in page.frames:
        try:
            btn = await fr.query_selector(_combined)
            if btn and await btn.is_visible():
                await btn.click(timeout=2000)
                await asyncio.sleep(0.3)
                _emit("dismiss_overlay", "fallback")
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
            await proactive.notify("navegador", _say().login_left_halfway.format(site=pend["sitio"]),
                                   kind="notify")
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


# Launch identity (profile dir, remote port, UA/stealth, locale) lives in launch_env.py — extracted
# 2026-08-29 (architecture ratchet). `_headless()` stays here: it couples to `_visible_override`.
from .launch_env import (_LAUNCH_ARGS, _STEALTH_JS, _UA, _browser_locale,  # noqa: F401
                         _profile_dir, _remote_port)


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
        port = _remote_port()                         # configurable through UI (settings.json) / env; never 9222/9200
        if port:
            args.append(f"--remote-debugging-port={port}")
            _emit("remote_port", f"puerto de depuración {port}")

        async def _launch(headless: bool, channel: str | None):
            # channel="chrome" = the installed REAL Chrome (real-browser fingerprint, not Playwright's Chromium that
            # anti-bot systems recognize). timezone_id keeps the zone consistent with the locale.
            _loc, _tz = _browser_locale()
            kw = dict(headless=headless, viewport=VIEWPORT, locale=_loc,
                      timezone_id=_tz, user_agent=_UA, args=args)
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
                               f"({_brief(e, 100)})")
        if _context is None:
            try:
                _context = await _launch(True, None)      # last resort: headless chromium
            except Exception as e:
                logger.warning(f"navegador: headless también falló ({_brief(e, 100)})")
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
        _write(loading=False, error=f"No pude abrir la página: {_brief(e, 200)}")
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

# CONFIRM-GATE deadline. Was 60 s, which is how long the answer takes when it comes from the card button next to
# the question. Through the CONVERSATION it cannot: the brain only learns the task is parked when it composes its
# next turn, asks then, and the operator answers on the turn after — 60 s expired mid-round-trip and the click
# was refused with the operator standing right there. 300 s is the sibling gate's TTL (`dispatch._CONFIRM_TTL`),
# chosen for the same reason: «¿de verdad lo compro?» arrives mid-conversation and deserves thinking time.
_CONFIRM_TIMEOUT = float(os.environ.get("NAVEGADOR_CONFIRM_TIMEOUT", "300"))
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
            tasks.milestone(task_id, "➡️ voy directo a la rejilla de resultados filtrada")
            await tb.agent_act("navigate", {"url": start_url})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"navegador: navigate inicial a resultados falló: {e}")
    try:
        res = await agent.run_task(goal, tb, plan=plan)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "summary": f"error del automatizador: {_brief(e, 160)}"}
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
    # V2-257 — the card stores the FACT, the sheet stores the FINDINGS. This path had never had a way to reach
    # the sheet: the engine's own loop does not talk to `widget_cli`, so what it found died in the card. It goes
    # AFTER completion, as in `dispatch._finalize_web` and for the same reason: it keeps `set_results` and the
    # final state required by the V2-192 invariant together (a LIVE task cannot have results).
    if results:
        try:
            from widgets.results import intake as _intake
            from .act_api import _sheet_of as _sheet_for
            _intake.push(results.get("items") or [], sheet=_sheet_for(task_id),
                         source_url=str((tasks.get(task_id) or {}).get("url") or ""))
        except Exception:  # noqa: BLE001
            pass
    try:
        from voice import brain_notes
        head = "completé" if (ok and success) else "no pude completar del todo"
        # V2-571 — a task with a SHEET has no separate card anymore: its browser renders inside the sheet's
        # Proceso tab, so the note must not name a card that does not exist (a surface named to the model that
        # is not on screen is how it narrates a screen the operator cannot see).
        _sheet = str((tasks.get(task_id) or {}).get("sheet") or "")
        tail = ("la pestaña de Proceso de esa misma hoja enseña por dónde fue el navegador." if _sheet else
                f"la tarjeta '{tasks.inst_id(task_id)}' solo enseña por dónde fue el navegador.")
        brain_notes.push(f"[SISTEMA] Navegador (tarea {task_id}): {head} «{goal}». {summary} Lo encontrado está "
                         f"en la hoja de resultados; {tail}")
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
            msg = f"Listo. {tail_}" if tail_ and tail_ != "sin resumen" else "Listo, lo tienes en la hoja de resultados."
        else:
            msg = (f"No pude terminarla del todo. {tail_}" if tail_ and tail_ != "sin resumen"
                   else "No pude terminarla del todo; lo que saqué está en la hoja de resultados.")
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
        tasks.milestone(task_id, f"⚠️ {_brief(e, 120)}")
    tasks.set_status(task_id, "open")
    tasks.set_phase(task_id, "abierto", False)


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
        _write(loading=False, error=f"No pude hacer clic: {_brief(e, 160)}")
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
def _stale_ref_reason(ref: int, refs: dict, snap_url: str, now_url: str) -> str:
    """Why that `ref` is invalid and WHAT to do, in one line the worker can use without guessing."""
    nums = sorted(int(k) for k in (refs or {}))
    if not nums:
        return (f"ref {ref}: todavía no has mirado esta página, así que no hay refs. Haz `look` y usa uno de los "
                f"que salgan.")
    rango = f"{nums[0]}..{nums[-1]}" if len(nums) > 1 else str(nums[0])
    if snap_url and now_url and snap_url != now_url:
        return (f"ref {ref} es de otra página: miraste «{snap_url[:80]}» y ahora estás en «{now_url[:80]}». Haz "
                f"`look` y usa un ref del listado NUEVO — los números se reparten al mirar, así que el {ref} de "
                f"antes no es el {ref} de ahora.")
    return (f"ref {ref} no está en la mirada actual, que tiene {rango}. Haz `look` para verla otra vez y usa uno "
            f"de esos números; no inventes refs ni reintentes el mismo.")


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
        # V2-358 — the HTTP STATUS of the page the tab is standing on, kept fresh by the response stream (goto
        # AND click-driven navigations). It is the wall signal no needle can miss: coches.net serves its block
        # with TWO different bodies («…eres un bot» and a bare «Ups! Parece que algo no va bien…») but the SAME
        # 403 — measured live 2026-08-27 (round 08:03: the worker hammered the identical URL four times, no
        # wall, no alts, sheet 0). Subresources never touch this: main-frame document responses only.
        self.last_status = 0
        def _on_response(r):
            try:
                if r.request.resource_type == "document" and r.frame == self.page.main_frame:
                    self.last_status = r.status
            except Exception:
                pass
        try:
            self.page.on("response", _on_response)
        except Exception:
            pass
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
        # V2-167 (second half): the tab is the ONLY place that holds both the URL and the text, so it is the only
        # place that can spot a wall served in the BODY with an ordinary URL (measured: entradas.com answering an
        # event page with an Akamai «Access Denied»). Bounded and best-effort — a capture must never fail because
        # the text could not be read, and the predicate that judges it only looks at short pages anyway.
        from . import tasks
        body = ""
        try:
            body = (await page.inner_text("body"))[:tasks.WALL_BODY_PEEK_CHARS]
        except Exception:
            pass
        tasks.update_view(self.task_id, url=page.url, page_title=title or page.url, shot_rev=self.rev,
                          page_text=body, status=int(getattr(self, "last_status", 0) or 0))
        self._emit("screenshot", page.url)

    async def _goto(self, url: str) -> None:
        page = await self.ensure()
        self._emit("navigate", url)
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await _dismiss_overlays(page)
            # AND IT RECORDS WHICH PAGE IT WAS DONE FOR. Without this, the sweep runs TWICE per navigation: here
            # and again in the look that follows, because the URL has just changed and that is precisely the
            # condition that triggers the sweep. It is the same toll just removed from `look`, charged through
            # the other gate.
            self._overlays_host = _host_of(getattr(page, "url", "") or url)
            await asyncio.sleep(0.35)
        except Exception as e:
            self._emit("nav_error", _brief(e, 160))
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
        # THE BANNER BELONGS TO NAVIGATION, NOT TO EACH LOOK. `_dismiss_overlays` waits 2.5 s for a known CMP
        # to appear and, if it does not, sweeps ALL frames × ALL selectors — and a site with ad iframes has many
        # frames. That full cost was paid on every `look`. Measured on the live es.wallapop.com setup, same page
        # and no banner: 11.17 · 11.23 · 11.45 s, three consecutive looks. It is not the cost of accepting
        # cookies once, but a fixed toll per action — and with the operator asking the worker to open tabs and
        # assess listings one by one, that toll is the ceiling.
        # Sweep when CHANGING pages, when a new banner may exist. If one appears late on the same URL, it appears
        # in the capture and the worker can click it: one automation is lost, not the result.
        _h = _host_of(getattr(page, "url", "") or "")
        if _h != getattr(self, "_overlays_host", None):
            await _dismiss_overlays(page)
            self._overlays_host = _h
        self.refs = {}
        # V2-248 — WHERE this look was taken. Stored so an expired `ref` can explain why it expired: if the page
        # is no longer the same, the reason is not that the number was written incorrectly.
        self.refs_url = getattr(page, "url", "") or ""
        # EACH DOM READ, BOUNDED. None of the three was: `query_selector_all` and `title()` hit the context's
        # default timeout and `evaluate` HAS NONE. And the costly part is not waiting, but what waiting TURNS
        # INTO: the action had already worked —the text had been entered— and the worker received "the browser
        # did not respond to type", that is, a failure, and repeated it. Here, whatever is available is returned,
        # SAYING that the view is incomplete, instead of bringing down an action that succeeded.
        _slow = []
        try:
            handles = await asyncio.wait_for(page.query_selector_all(_INTERACTIVE), _DOM_TIMEOUT_S)
        except Exception:
            handles, _ = [], _slow.append("elementos")
        try:
            metas = await asyncio.wait_for(_bulk_metas(page), _DOM_TIMEOUT_S)
        except Exception:
            metas, _ = {}, _slow.append("etiquetas")
        lines = _snapshot_lines(handles, metas, self.refs)
        title = ""
        try:
            title = await asyncio.wait_for(page.title(), _DOM_TIMEOUT_S)
        except Exception:
            _slow.append("título")
        out = {"url": page.url, "title": title or "", "elements": "\n".join(lines)}
        if _slow:
            # NAME what there was not time to read and say what to do, instead of presenting a partial view as
            # though it were the whole page —which is how a worker concludes "there is nothing here" about a
            # full listing. Same contract as node 4.20: the bridge says what it knows.
            out["partial"] = ", ".join(_slow)
            out["note"] = (f"la página seguía cargando y no dio tiempo a leer: {out['partial']}. "
                           f"La acción SÍ se hizo. Vuelve a mirar con «look» antes de decidir nada.")
        return out

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
                # V2-152: reaching a page is a MILESTONE by this module's own definition (what the task DID, not
                # every click), and nothing in the worker-driven path ever appended one — `_automate` pushes the
                # milestones and that is the built-in loop, not the path a Brain Worker drives. So `steps` was
                # structurally 0 and `last_event` empty for the whole life of a worker task, and the brain had a
                # step COUNT of zero to answer «¿cómo va?» with. `_goto` already captures the view on success, so
                # `url` is not the gap here; the FEED is.
                from . import tasks
                tasks.milestone(self.task_id, f"🌐 abrió {page.url[:120]}")
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
                # V2-711 T1 — this pressed Enter with NO gate of any kind, and Enter inside a form is a
                # submit: the same consequence as the click the gate next door was guarding. Gated on the
                # FOCUSED element, which is what Enter acts on.
                key = str(args.get("key", "Enter")) or "Enter"
                if key.lower() in ("enter", "numpadenter", "return"):
                    ok, why = await self._may_act(page, None)
                    if not ok:
                        return False, why
                try:
                    await page.keyboard.press(key)
                    await asyncio.sleep(0.5)
                except Exception:
                    pass
                await self._capture()
                return True, "tecla pulsada"
            if action in ("click_at", "type_at"):
                x, y = float(args.get("x", 0)), float(args.get("y", 0))
                # V2-711 T1 — the VISION route, which `nucleo/nav_cli.py` RECOMMENDS to the worker («VISION
                # flow (robust for forms)»), reached the mouse with no gate at all: the recommended path was
                # the unguarded one. The element under the pixel is resolved BEFORE the mouse moves.
                if action == "click_at":
                    ok, why = await self._may_act(page, None, at=(x, y))
                    if not ok:
                        return False, why
                self._emit("vision_" + ("click" if action == "click_at" else "type"), f"{int(x)},{int(y)}")
                await _human_click_at(page, x, y, self.mouse)
                if action == "type_at":
                    await page.keyboard.type(str(args.get("text", "")), delay=random.randint(40, 120))
                    if bool(args.get("submit")):
                        # `--submit` is an Enter, and an Enter in a form submits it. Same gate, same reason.
                        ok, why = await self._may_act(page, None)
                        if not ok:
                            return True, "texto escrito; NO enviado: " + why
                        await asyncio.sleep(random.uniform(0.2, 0.5))
                        await page.keyboard.press("Enter")
                await asyncio.sleep(0.7)
                await self._reap_popups()
                await self._capture()
                return True, ("clic" if action == "click_at" else "texto") + " (visión) hecho"
            ref = int(args.get("ref", 0))
            h = self.refs.get(ref)
            if h is None:
                # V2-248 — AN EXPIRED REF SAID WHAT WAS HAPPENING BUT NOT HOW TO RECOVER. Same contract as node 4.20
                # and V2-203: the bridge SAYS what it knows, and an error also says how to recover. Measured by the
                # harness on 2026-08-21 (`ref 26 does not exist`, the V2-212 form): it is one of the three causes
                # that made a worker die on its own, while the recovery —look again— was one command away.
                #
                # It is deliberately NOT retried using only the new snapshot: numbers are ASSIGNED during a look,
                # so 26 in the new look is a different element. Retrying would click something else.
                return False, _stale_ref_reason(ref, self.refs, getattr(self, "refs_url", ""),
                                                getattr(page, "url", "") or "")
            if action == "click":
                # CONFIRM-GATE (safety): if the click looks IRREVERSIBLE, STOP and ask the operator for OK
                # BEFORE clicking. The automator never buys/publishes/deletes/books blindly.
                # V2-711 T1: this used to be the ONLY gated route and it judged the LABEL alone — 21 of 30
                # real button labels walked through it, «Reservar» and «Confirmar reserva» among them — and
                # it failed OPEN when the element could not be described. All four routes share `_may_act`
                # now, which reads the element's CONTEXT as well as its words and fails CLOSED.
                ok, why = await self._may_act(page, h)
                if not ok:
                    return False, why
                await _human_click_handle(page, h, self.mouse)
                await asyncio.sleep(0.7)
                await self._reap_popups()                     # TASK 3: absorb/close popups → no accumulated tabs
                await self._capture()
                return True, "clic hecho"
            if action == "type":
                # Typing is harmless; `--submit` presses Enter inside the helper, which is not (V2-711 T1).
                _submit = bool(args.get("submit"))
                if _submit:
                    ok, why = await self._may_act(page, h)
                    if not ok:
                        await _human_type_handle(page, h, str(args.get("text", "")), False, self.mouse)
                        await self._capture()
                        return True, "texto escrito; NO enviado: " + why
                await _human_type_handle(page, h, str(args.get("text", "")), _submit, self.mouse)
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
                    return False, f"no pude seleccionar «{val or idx}» en el desplegable: {_brief(e, 80)}"
                await asyncio.sleep(0.4)
                await self._capture()
                return True, f"opción «{val or idx}» seleccionada"
        except Exception as e:
            return False, f"{type(e).__name__}: {_brief(e, 120)}"
        return False, f"acción desconocida: {action}"

    async def _may_act(self, page, handle, at: tuple[float, float] | None = None) -> tuple[bool, str]:
        """THE ONE GATE in front of an irreversible click (V2-711 T1). All four routes that reach the mouse
        or the keyboard consult it BEFORE moving anything; the decision itself lives in `click_gate`."""
        return await _click_gate.may_act(page, handle, at, confirm=self._confirm, task_id=self.task_id)

    async def _confirm(self, label: str) -> bool:
        """Ask the operator for OK on an irreversible action and WAIT for the response (by voice, routed to this task).
        Returns True if approved. Timeout ~60s → do not execute (fail-safe). Cancellable."""
        from . import tasks
        tasks.ask(self.task_id, f"Voy a pulsar «{label[:50]}». ¿Lo confirmo? (dime sí o no)")
        try:
            from voice import proactive
            await proactive.notify("navegador",
                                   _say().click_needs_ok.format(task=self.task_id, label=label[:40]),
                                   kind="notify")
        except Exception:
            pass
        for _ in range(int(_CONFIRM_TIMEOUT / 0.5)):
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

    async def visit(self, url: str, chars: int = 2500) -> dict:
        """Open a listing in ANOTHER tab, read it, and close it — without moving the listing tab.

        Operator request (2026-08-24): «the brain worker itself must extract data, model the different listings,
        open enough tabs to investigate, and assess each result listing». It could not do that before: the bridge
        only knew `navigate`, which takes over the ONLY tab —so inspecting one listing meant losing the results and
        searching for it again, two 7-11 s navigations per listing, with the search and filters in between.

        It returns what is needed to ASSESS a listing: its title, truncated listing text, and the listings declared
        by the page itself (price, image). Not a capture: assessing ten listings by vision means ten PNG reads,
        and this must be possible many times.

        The tab is ALWAYS closed, including if reading fails —one orphaned tab per listing is how it reaches the
        thirty already measured by `_reap_popups`. And `self.page` is untouched on every path: the results remain
        where they were, which is the reason this verb exists.
        """
        page = await self.ensure()
        try:
            ctx = page.context
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": _brief(e, 120)}
        tab = None
        try:
            tab = await ctx.new_page()
            await tab.goto(_normalize_url(url), wait_until="domcontentloaded")
            # No banner sweep: the listing is read, not driven, and the sweep is the toll just removed from the
            # hot path. A banner covers the view, not the text.
            title, body, items = "", "", []
            try:
                title = await asyncio.wait_for(tab.title(), _DOM_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
            try:
                # THE CONTENT, NOT THE MENU. `body.innerText` starts with navigation chrome —measured in the first
                # test: «Todas las categorías Coches Motos Motor y accesorios…»— and with truncated text that
                # leaves the worker assessing a listing by the site's menu. It is the same pattern V2-234 measured
                # during extraction, through the other entry point.
                #
                # The rule is STRUCTURAL, not a site list: if the page declares its main content (`main`, `article`,
                # `[role=main]`), read that; otherwise read the entire body, which is what existed. Do not truncate
                # by position or guess where the menu ends.
                body = await asyncio.wait_for(tab.evaluate(
                    "() => { const m = document.querySelector('main, article, [role=main]');"
                    "        return ((m || document.body || {}).innerText) || ''; }"), _DOM_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
            try:
                items = await asyncio.wait_for(tab.evaluate(_JS_EXTRACT, 6), _DOM_TIMEOUT_S) or []
            except Exception:  # noqa: BLE001
                items = []
            return {"ok": True, "url": tab.url, "title": title or "",
                    "text": " ".join((body or "").split())[:max(200, int(chars))],
                    "listings": items}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": _brief(e, 140), "url": url}
        finally:
            try:
                if tab and not tab.is_closed():
                    await tab.close()
            except Exception:  # noqa: BLE001
                pass

    async def close(self) -> None:
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        self.page = None


# V2-778 F1 — moved to `owner_login.py`, imported back under their names (that module reads this one).
from .owner_login import (  # noqa: E402,F401
    _login_url_for, _click_login_affordance, _reach_login, _cookie_fingerprint, _authenticate, _begin_login,
    _arm_login_watch, _is_logged_in, _login_watch, _auth_done, _resume_paused_tasks, _in_container,
    _fail_paused_tasks, _LOGIN_STRICT_RE, _find_login_affordance, _already_authenticated, _probe_logged_in,
    _login_site_of)
