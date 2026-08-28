"""navegador/launch_env.py — what the launched task browser PRESENTS and where its identity lives.

Extracted from `owner.py` (architecture ratchet, 2026-08-29): the persistent profile, the remote-debug
port, the UA/stealth surface and the locale+timezone are one coherent concern — the browser's outward
identity — and none of them touch the live page state that `owner.py` orchestrates. `_headless()` stays
in `owner.py` on purpose: it couples to `_visible_override`, which `authenticate` flips at runtime.
"""
from __future__ import annotations

import os

from .. import store

WID = "navegador"

def _profile_dir() -> str:
    """PERSISTENT and ISOLATED profile (cookies/session/logins are saved on disk → no need to re-enter credentials).
    Lives inside the widget, separate from your Chrome and your 9222 automation: it NEVER shares your own profile.

    Keyed by the locale the browser PRESENTS (V2-469): declaring en-US at launch is not enough when the
    cookies were acquired declaring es-ES — the site remembers the contradiction longer than the
    declaration. Measured 2026-08-29 (`cheapest-monitor__us`, worker session 085b1384): Amazon kept
    serving «Deliver to Spain» EUR prices to the en-US browser and the worker burned ~80s fighting the
    currency before giving up. es-ES keeps the legacy `profile` name so existing saved logins stay."""
    loc, _tz = _browser_locale()
    name = "profile" if loc == "es-ES" else f"profile-{loc}"
    d = os.path.join(store.data_dir(WID), name)
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


def _browser_locale() -> tuple:
    """Locale+timezone the task browser PRESENTS, paired — following the engine's language (V2-469).

    They were pinned to es-ES/Europe/Madrid for every engine: measured in `cheapest-monitor__us` (worker
    session 79bfd2ce), Amazon.com served product pages in SPANISH on the US agent and Best Buy answered
    «Select your Country» — a site localizes by what the browser declares, and the declaration outranked
    the engine. Same reason and same shape as websearch's Accept-Language fix (V2-411): engine language,
    env escape hatches (NAVEGADOR_LOCALE / NAVEGADOR_TZ), Spanish as the fallback of always. Read at
    LAUNCH: a language switch mid-session applies when the persistent context is next recreated.
    """
    env_loc = os.environ.get("NAVEGADOR_LOCALE", "").strip()
    env_tz = os.environ.get("NAVEGADOR_TZ", "").strip()
    if env_loc:
        return env_loc, (env_tz or ("Europe/Madrid" if env_loc.startswith("es") else "America/New_York"))
    try:
        from voice.engine.core import langs as _langs
        code = (_langs.current_code() or "es").lower()
    except Exception:  # noqa: BLE001 — the browser must never die because the language is unreadable
        code = "es"
    if code == "en":
        return "en-US", (env_tz or "America/New_York")
    if code == "es":
        return "es-ES", (env_tz or "Europe/Madrid")
    return f"{code}-{code.upper()}", (env_tz or "Europe/Madrid")
