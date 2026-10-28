"""Watching the login window until the session is established, then resuming the paused tasks; and the headless
probes that tell whether a site already has a session."""
from __future__ import annotations

from widgets.navegador import owner as _o


def _arm_login_watch(task_id: str, site: str) -> None:
    """(Re)arm the POLLER that watches the login window (auto-detection + soft timeout)."""
    old = _o._login_timeouts.pop(task_id, None)
    if old:
        old.cancel()
    t = _o.asyncio.create_task(_o._login_watch(task_id, site))
    _o._login_timeouts[task_id] = t
    _o._running.add(t)
    t.add_done_callback(_o._running.discard)


async def _is_logged_in(task_id: str, tb, site: str) -> bool:
    """Is the session established? VERSATILE signal (without guessing per-site cookie names): the page is NO LONGER a
    login/registration page AND NEW cookies appeared compared with the moment login opened (navigating login by itself
    does not create a session; signing in does leave cookies and redirects away from the form)."""
    from widgets.navegador import agent
    try:
        state = await tb.snapshot_for_agent()
    except Exception:
        return False
    url = state.get("url", "")
    if agent._looks_like_login(url, state.get("elements", "")) or _o._REGISTER_TEXT_RE.search(url):
        return False                                              # still on login/registration
    new_cookies = await _o._cookie_fingerprint(tb) - _o._auth_baseline_cookies.get(task_id, set())
    return len(new_cookies) >= 1


async def _login_watch(task_id: str, site: str) -> None:
    """WATCH the login window: every `_LOGIN_POLL`s, capture the page (the card shows it live) and check whether the
    session is established; 2 consecutive positive reads trigger `_auth_done` ALONE (zero manual steps).
    `_LOGIN_TIMEOUT` unfinished → soft reminder, no kill. The button/voice remain as a safety net."""
    from widgets.navegador import tasks
    stable = 0
    waited = 0.0
    reminded = False
    try:
        while True:
            await _o.asyncio.sleep(_o._LOGIN_POLL)
            waited += _o._LOGIN_POLL
            t = tasks.get(task_id)
            if not t or not t.get("awaiting_login"):
                return                                            # resolved another way (button/voice/cancel)
            tb = _o._task_browsers.get(task_id)
            if tb is None:
                return
            try:
                await tb._capture()                               # refresh the live capture in the card
            except Exception:
                pass
            stable = stable + 1 if await _o._is_logged_in(task_id, tb, site) else 0
            if stable >= 2:                                       # confirmed in 2 reads → close by itself
                tasks.milestone(task_id, "✅ Detecté que ya iniciaste sesión")
                await _o._auth_done(task_id)
                return
            if not reminded and waited >= _o._LOGIN_TIMEOUT:
                reminded = True
                tasks.milestone(task_id, "⏰ Sigo vigilando la ventana de login; tómate tu tiempo.")
                try:
                    from voice import proactive
                    await proactive.notify("navegador", f"Sigo pendiente de tu login en {site}, sin prisa.",
                                           kind="notify")
                except Exception:
                    pass
    except _o.asyncio.CancelledError:
        return


async def _auth_done(task_id: str) -> None:
    """The operator finished signing in → return to HEADLESS; the session remains in the persistent profile (cookies on
    disk). PROBE that the session really stuck; if so, record the ESTABLISHED breadcrumb in memory, clear the
    half-finished checkpoint, and RESUME (automatically) the paused tasks. Close the visible window (clean desktop)."""
    from widgets.navegador import auth_memory, tasks
    w = _o._login_timeouts.pop(task_id, None)
    if w and w is not _o.asyncio.current_task():
        w.cancel()                                    # stop the poller (unless it is the caller)
    _o._auth_baseline_cookies.pop(task_id, None)
    _o._visible_override = False                         # return to headless
    if task_id:
        tasks.set_login_wait(task_id, False)
        tasks.set_phase(task_id, "sesión guardada", False)
        tasks.milestone(task_id, "✅ Sesión guardada en el perfil")
        _o._task_browsers.pop(task_id, None)
    await _o.stop()                                      # close the window; the profile (cookies) persists → relaunch headless
    site = _o._auth_active or (_o._auth_resume.get(task_id) or {}).get("site") or ""
    # POST-LOGIN PROBE: did the session stick or did we bounce back to login? (best-effort → if unsure assume OK, do not block).
    if site and not await _o._probe_logged_in(site):
        tasks.milestone(task_id, "⚠️ No detecté la sesión iniciada; puede que el login no se completara.")
        auth_memory.checkpoint_auth_pending(site, task_id, (_o._auth_resume.get(task_id) or {}).get("goal", ""))
        _o._auth_active = ""
        try:
            from voice import proactive
            await proactive.notify("navegador",
                                   _o._say().login_not_saved.replace("{site}", str(site)),
                                   kind="notify")
        except Exception:
            pass
        return
    if site:
        auth_memory.record_session_established(site)  # recallable ESTABLISHED marker (the secret stays only in the profile)
    auth_memory.clear_auth_pending()
    _o._auth_active = ""
    await _o._resume_paused_tasks()
    try:
        from voice import proactive
        await proactive.notify("navegador", "Sesión guardada, sigo con lo tuyo.", kind="notify")
    except Exception:
        pass


async def _resume_paused_tasks() -> None:
    """Resume (re-enqueue `automate`) ALL tasks recorded when login started: the requester + paused tasks. Drains
    `_auth_resume`. Cancelled tasks or tasks without an objective are discarded."""
    from widgets.navegador import tasks
    items = list(_o._auth_resume.items())
    _o._auth_resume.clear()
    for tid, info in items:
        goal = (info or {}).get("goal", "")
        if not goal or tasks.is_cancelled(tid):
            continue
        tasks.set_status(tid, "queued")
        tasks.milestone(tid, "▶️ reanudo la tarea, ya autenticado")
        _t = _o.asyncio.create_task(_o._automate(goal, (info or {}).get("plan", ""), tid))
        _o._running.add(_t)
        _t.add_done_callback(_o._running.discard)


# Only STRONG login intent for detecting "sign-in required" (not ambiguous text like "my account"/"enter", which also
# appears WHILE logged in → false positives).
_LOGIN_STRICT_RE = _o.re.compile(r"(iniciar sesi[oó]n|inicia sesi[oó]n|log ?in|sign ?in)", _o.re.I)


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
        if txt and _o._LOGIN_STRICT_RE.search(txt) and not _o._REGISTER_TEXT_RE.search(txt):
            try:
                if await el.is_visible():
                    return True
            except Exception:
                return True
    return False


async def _already_authenticated(site: str) -> bool:
    """Is there ALREADY a session on `site`? Navigate headless and verify it is NOT a login screen AND shows NO visible
    'sign in' button — so login is never reopened when already inside. Best-effort: in doubt return False (better to
    check login than act without an account)."""
    if not site:
        return False
    from widgets.navegador import agent
    try:
        page = await _o._ensure_page()
        url = site if site.startswith("http") else f"https://{site.strip('/')}"
        await page.goto(url, wait_until="domcontentloaded")
        await _o._dismiss_overlays(page)
        await _o.asyncio.sleep(0.5)
        if agent._looks_like_login(page.url or "", ""):
            return False
        return not await _o._find_login_affordance(page)
    except Exception:
        return False


async def _probe_logged_in(site: str) -> bool:
    """Navigate to the site (headless) and verify it does NOT bounce to a login screen → the session stuck. Reuses the
    `agent._looks_like_login` detector. Best-effort: any failure → True (do not block on a doubtful probe)."""
    if not site:
        return True
    from widgets.navegador import agent
    try:
        page = await _o._ensure_page()
        url = site if site.startswith("http") else f"https://{site}"
        await page.goto(url, wait_until="domcontentloaded")
        await _o._dismiss_overlays(page)
        await _o.asyncio.sleep(0.4)
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
