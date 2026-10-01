"""The browser's PAGE: launching Chromium and keeping one live page, URL normalising, the cursor overlay, the
capture the widget shows, and navigation with its own history (V2-778 F1, 2026-10-01).

Moved out of `widgets/navegador/owner.py` with no behaviour change. Every module-level name these functions read —
each other included — is read through the owner (`_o.<name>`), so a patch on `owner` still governs every call, and
the owner imports them back. The browser's state (`_pw`, `_browser`, `_context`, `_page`, `_rev`, the history)
stays the owner's: what was `global` there is `_o.<name>` here.
"""
from __future__ import annotations

from widgets.navegador import owner as _o


async def _ensure_page():
    """ONE real window (headed) with a PERSISTENT PROFILE and lazy startup. Reuses any existing window/tab (never opens
    one window per request → no desktop clutter). Isolated profile: does not touch your Chrome or your 9222/9200
    browser (own process and instance). If the real window fails (no display), degrades to headless so the widget is
    not left dead. Lazy Playwright import: if the dependency is missing, only this widget degrades."""
    if _o._page is not None and not _o._page.is_closed():
        return _o._page
    from playwright.async_api import async_playwright
    if _o._pw is None:
        _o._pw = await async_playwright().start()
    if _o._context is None:
        # OPTIONAL debugging port chosen by env — NEVER yours (9222/9200). Empty = Playwright internal pipe
        # (zero ports, zero collisions). If you want to attach, set NAVEGADOR_REMOTE_PORT to a different port.
        args = list(_o._LAUNCH_ARGS)
        port = _o._remote_port()                         # configurable through UI (settings.json) / env; never 9222/9200
        if port:
            args.append(f"--remote-debugging-port={port}")
            _o._emit("remote_port", f"puerto de depuración {port}")

        async def _launch(headless: bool, channel: str | None):
            # channel="chrome" = the installed REAL Chrome (real-browser fingerprint, not Playwright's Chromium that
            # anti-bot systems recognize). timezone_id keeps the zone consistent with the locale.
            _loc, _tz = _o._browser_locale()
            kw = dict(headless=headless, viewport=_o.VIEWPORT, locale=_loc,
                      timezone_id=_tz, user_agent=_o._UA, args=args)
            if channel:
                kw["channel"] = channel
            return await _o._pw.chromium.launch_persistent_context(_o._profile_dir(), **kw)

        # Prefer REAL Chrome (less detectable). If it is not installed, fall back to Playwright's Chromium; if there
        # is no display (headed fails), fall back to headless. Never leave the widget dead.
        _o._context = None
        for _ch in ("chrome", None):
            try:
                _o._context = await _launch(_o._headless(), _ch)
                break
            except Exception as e:
                _o.logger.warning(f"navegador: launch channel={_ch or 'chromium'} falló "
                               f"({_o._brief(e, 100)})")
        if _o._context is None:
            try:
                _o._context = await _launch(True, None)      # last resort: headless chromium
            except Exception as e:
                _o.logger.warning(f"navegador: headless también falló ({_o._brief(e, 100)})")
                raise
        _o._browser = None                               # the persistent context IS the browser (no separate object)
        try:
            await _o._context.add_init_script(_o._STEALTH_JS)   # stealth: browse like a human, not like a scraper
        except Exception:
            pass
        _o._context.set_default_navigation_timeout(_o._NAV_TIMEOUT)
        _o._context.set_default_timeout(_o._NAV_TIMEOUT)
        # Google/YouTube consent in the EU: cookies that avoid the wall (best effort). With the persistent profile,
        # once a banner is accepted it is also saved → it stops appearing on subsequent visits.
        try:
            await _o._context.add_cookies([
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
    _o._page = _o._context.pages[0] if _o._context.pages else await _o._context.new_page()
    _o._emit("launched", f"navegador {'headless' if _o._headless() else 'ventana real'} · perfil persistente")
    return _o._page


# ── utilities ────────────────────────────────────────────────────────────────────────────────────────────────
_YT_RE = _o.re.compile(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([0-9A-Za-z_-]{11})")
_YT_ID_RE = _o.re.compile(r'"videoId":"([0-9A-Za-z_-]{11})"')


def _looks_like_url(s: str) -> bool:
    s = (s or "").strip()
    if not s or " " in s:
        return False
    if s.startswith(("http://", "https://")):
        return True
    return bool(_o.re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+(/.*)?$", s, _o.re.I))   # domain with TLD


def _normalize_url(s: str) -> str:
    s = (s or "").strip()
    if not s.startswith(("http://", "https://")):
        s = "https://" + s
    return s


def _youtube_id(s: str) -> str:
    m = _o._YT_RE.search(s or "")
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
    page = _o._page
    shot = f"{_o.store.data_dir(_o.WID)}/shot.png"
    await page.screenshot(path=shot, type="png", full_page=False)
    if _o._automating:                                     # running task → draw the virtual cursor where it is acting
        # OFF-LOOP (V2-035): the PIL composite is synchronous CPU work that held the GIL in the uvicorn loop and
        # starved the TTS audio pump (choppy voice). Move it to a thread → it does not block voice.
        await _o.asyncio.to_thread(_o._draw_cursor, shot, _o._mouse["x"], _o._mouse["y"])
    _o._rev += 1
    title = ""
    try:
        title = await page.title()
    except Exception:
        pass
    _o._write(mode="page", url=page.url, title=title or page.url, rev=_o._rev, loading=False, error="",
           youtube_id="", youtube_title="")
    _o._emit("screenshot", page.url, rev=_o._rev)


async def _goto(url: str, push: bool = True) -> None:
    page = await _o._ensure_page()
    _o._write(loading=True, error="", url=url)
    _o._emit("navigate", url)
    try:
        await page.goto(url, wait_until="domcontentloaded")
        await _o._dismiss_overlays(page)                    # close cookie banners that block the website
        await _o.asyncio.sleep(0.35)                     # let the above-the-fold render before the screenshot
    except Exception as e:
        _o._write(loading=False, error=f"No pude abrir la página: {_o._brief(e, 200)}")
        _o._emit("nav_error", url, error=str(e)[:200])
        return
    if push:
        _o._hist = _o._hist[:_o._idx + 1] + [page.url]
        _o._idx = len(_o._hist) - 1
    await _o._capture()
