#
# owner.py — live BACKEND for the "navegador" widget (kind:"backed"). It is the ONLY writer to
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

from widgets import store
from widgets.navegador import click_gate as _click_gate, click_reason as _click_reason
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


_visible_override = None   # None = normal; True = force visible (login); False = force headless. Used by authenticate.


# Launch identity (profile dir, remote port, UA/stealth, locale) lives in launch_env.py — extracted
# 2026-08-29 (architecture ratchet). `_headless()` stays here: it couples to `_visible_override`.
from widgets.navegador.launch_env import (_LAUNCH_ARGS, _STEALTH_JS, _UA, _browser_locale,  # noqa: F401
                         _profile_dir, _remote_port)


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


# DOM/accessibility snapshot + human-like input primitives moved to dom.py (2026-08-17 modularization
# pass) — page-parametric, no module-global coupling. Re-exported here since TaskBrowser's own methods
# below reference these as bare names.
from widgets.navegador.dom import (  # noqa: F401 — re-export
    _DANGER_RE, _INTERACTIVE, _JS_EXTRACT, _describe_el, _JS_DESCRIBE, _bulk_metas, _snapshot_lines,
    _human_move, _human_click_handle, _human_type_handle, _human_click_at,
)


# V2-778 F1 — moved to `owner_login.py`, imported back under their names (that module reads this one).
from widgets.navegador.owner_login import (  # noqa: E402,F401
    _login_url_for, _click_login_affordance, _reach_login, _cookie_fingerprint, _authenticate, _begin_login,
    _arm_login_watch, _is_logged_in, _login_watch, _auth_done, _resume_paused_tasks,
    _LOGIN_STRICT_RE, _find_login_affordance, _already_authenticated, _probe_logged_in,
    _login_site_of)


# V2-778 F1 — moved to `owner_actions.py`, imported back under their names (that module reads this one).
from widgets.navegador.owner_actions import (  # noqa: E402,F401
    _automate, _browse, _close_task, _search, _step, _scroll, _click, _type, _press, _youtube, _show_youtube)


# V2-778 F1 — moved to `owner_page.py`, imported back under their names (that module reads this one).
from widgets.navegador.owner_page import (  # noqa: E402,F401
    _ensure_page, _YT_RE, _YT_ID_RE, _looks_like_url, _normalize_url, _youtube_id, _draw_cursor, _capture, _goto)

# refactor2710-12 — the owner's own code lives in its concern modules; the STATE above stays here, and they read it
# (and every other name of this module) through the package, like the three siblings above.
from widgets.navegador.owner.lifecycle import (  # noqa: E402,F401 — re-export
    start, stop, _close_browser, _headless)
from widgets.navegador.owner.handle import (  # noqa: E402,F401 — re-export
    _host_of, _dismiss_overlays, handle, _stale_ref_reason)
from widgets.navegador.owner.browser_steps import (  # noqa: E402,F401 — re-export
    _StepsMixin)
from widgets.navegador.owner.browser_page import (  # noqa: E402,F401 — re-export
    _PageMixin)
from widgets.navegador.owner.browser import (  # noqa: E402,F401 — re-export
    TaskBrowser)
