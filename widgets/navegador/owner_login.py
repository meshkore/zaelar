"""The browser's LOGIN flow: reaching a site's login, the visible window the operator signs in through, watching
for the session, and resuming the tasks that were waiting for it (V2-778 F1, 2026-10-01).

Moved out of `widgets/navegador/owner.py` (1,713 lines) with no behaviour change. Every module-level name these
functions read — each other included — is read through the owner (`_o.<name>`), so a patch on `owner` still
governs every call, and the owner imports them back under their names. The two pieces of module state the login
flips (`_visible_override`, `_auth_active`) stay the owner's: what was `global` there is `_o.<name>` here.
"""
from __future__ import annotations

from widgets.navegador import owner as _o


def _login_url_for(site: str) -> str | None:
    """KNOWN login URL for `site` (domain), or None. Matches by base domain (sub.domain.tld → domain.tld)."""
    host = (site or "").strip().lower()
    host = host.replace("https://", "").replace("http://", "").split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    for key, u in _o._LOGIN_URLS.items():
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
        if not blob.strip() or not _o._LOGIN_TEXT_RE.search(blob):
            continue
        # registration affordance (and its own text does not say login) → skip it, never land on registration
        if _o._REGISTER_TEXT_RE.search(blob) and not _o._LOGIN_TEXT_RE.search(txt):
            continue
        best = el
        if _o._LOGIN_TEXT_RE.search(txt):                # prioritize the element whose own text says "sign in"
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
    known = _o._login_url_for(site)
    target = known or (site if site.startswith("http") else f"https://{site.strip('/')}")
    try:
        await tb.open_target(target)
    except Exception:
        pass
    if tb.page is None:
        return
    await _o._dismiss_overlays(tb.page)
    try:
        state = await tb.snapshot_for_agent()
    except Exception:
        state = {"url": tb.page.url, "elements": ""}
    if agent._looks_like_login(state.get("url", ""), state.get("elements", "")):
        return                                        # the known URL already left us on login
    await _o._click_login_affordance(tb.page)            # versatile: find and click "sign in"
    await _o._dismiss_overlays(tb.page)


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
    from . import agent, auth_memory, tasks
    url = (url or "wallapop.com").strip()
    site = (site or _o._login_site_of(url)).strip().lower()
    if not task_id:
        task_id = tasks.create(f"Iniciar sesión · {site or url}", title=f"Login · {site or url}")
    _o._auth_resume.setdefault(task_id, {"goal": goal, "plan": plan, "site": site})
    # GUARD: is there ALREADY a session? Then do NOT open any login — confirm it and continue the task (bug: it
    # reopened Wallapop login while already authenticated). Headless check, no window.
    if await _o._already_authenticated(site):
        auth_memory.record_session_established(site)
        # search objective to resume: the task's objective, or the one left in the memory checkpoint (auth_pending).
        pend = auth_memory.read_auth_pending() or {}
        goal_to_run = ((_o._auth_resume.get(task_id) or {}).get("goal") or goal or pend.get("objetivo") or "").strip()
        auth_memory.clear_auth_pending()
        tasks.set_login_wait(task_id, False)
        tasks.milestone(task_id, f"✅ Ya había sesión en «{site}» — no hace falta iniciar sesión")
        try:
            from voice import proactive
            await proactive.notify("navegador", _o._say().login_already_in.format(site=site), kind="notify")
        except Exception:
            pass
        if goal_to_run:                                          # search to resume → launch it now (authenticated)
            tasks.set_phase(task_id, "retomando la búsqueda", True)
            _o._auth_resume.pop(task_id, None)
            _t = _o.asyncio.create_task(_o._automate(goal_to_run, "", task_id))
            _o._running.add(_t)
            _t.add_done_callback(_o._running.discard)
        else:                                                     # no objective (standalone login) → close the card, not left hanging
            tasks.set_phase(task_id, "ya tenías sesión", False)
            tasks.finish(task_id, "done", "Ya tenías sesión iniciada.")
        await _o._resume_paused_tasks()                              # resume OTHER tasks paused by login (if any)
        return
    if _o._in_container():
        # 2026-08-03: in a headless container (cloud) there is no display → the "headed" relaunch below ALWAYS
        # silently degrades to headless (`_ensure_page`), and the task waits for a login that can never happen —
        # previously this looped forever (voice AND widget hung, observed live with Wallapop). Stop here, BEFORE
        # trying, with a clear message instead of a phantom attempt.
        msg = (f"Para entrar en {site or url} hace falta iniciar sesión, y eso todavía no lo puedo hacer desde la "
               "nube — necesitaría abrir una ventana de navegador que aquí no existe. Instala la versión local "
               "(desde GitHub) si quieres usar sitios que exigen iniciar sesión.")
        await _o._fail_paused_tasks(msg)
        try:
            from voice import proactive
            await proactive.notify("navegador", msg, speak=True)
        except Exception:
            pass
        return
    _o._auth_active = site
    auth_memory.checkpoint_auth_pending(site, task_id, goal)       # durable breadcrumb (survives crash/restart)
    _o._visible_override = True                                       # force VISIBLE for login
    await _o.stop()                                                  # relaunch headed (profile/cookies persist)
    _o._task_browsers.pop(task_id, None)
    tb = _o.TaskBrowser(task_id)
    _o._task_browsers[task_id] = tb
    tasks.set_status(task_id, "needs_input")
    tasks.set_phase(task_id, "esperando tu inicio de sesión", True)
    tasks.set_login_wait(task_id, True)
    try:
        if agent._LOGIN_URL_RE.search(url.lower()):               # already IS a login URL (need_login path) → open it
            await tb.open_target(url)
            if tb.page is not None:
                await _o._dismiss_overlays(tb.page)
        else:                                                     # site/domain → RESOLVE login (versatile)
            await _o._reach_login(tb, site or url)
    except Exception as e:  # noqa: BLE001
        tasks.milestone(task_id, f"⚠️ {_o._brief(e, 100)}")
    _o._auth_baseline_cookies[task_id] = await _o._cookie_fingerprint(tb)
    tasks.milestone(task_id, "🔓 Inicia sesión en la ventana; lo detecto solo cuando entres — no tienes que hacer nada más")
    try:
        from voice import proactive
        await proactive.notify("navegador", _o._say().login_opened, speak=True)   # V2-676: from the table
    except Exception:
        pass
    _o._arm_login_watch(task_id, site)                               # WATCH the window → auto-detect login


async def _begin_login(task_id: str, site: str, login_url: str, goal: str = "", plan: str = "") -> None:
    """A login wall stopped a task. PAUSE the other active tasks (one window → headed relaunch kills their tabs), record
    them for resumption, and open the login window (which watches itself). They resume in auth_done."""
    from . import tasks
    site = (site or _o._login_site_of(login_url)).strip().lower()
    _o._auth_resume[task_id] = {"goal": goal, "plan": plan, "site": site}
    for other in list(tasks.active_ids()):
        if other == task_id:
            continue
        ot = tasks.get(other)
        if ot.get("goal"):
            _o._auth_resume.setdefault(other, {"goal": ot["goal"], "plan": "", "site": site})
        tasks.set_status(other, "needs_input")
        tasks.milestone(other, "⏸ en pausa mientras inicias sesión; la reanudo al terminar")
    await _o._authenticate(task_id, login_url, site=site, goal=goal, plan=plan)


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
    from . import agent
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
    from . import tasks
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
    from . import auth_memory, tasks
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
    from . import tasks
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
    items = list(_o._auth_resume.items())
    _o._auth_resume.clear()
    for tid, _info in items:
        if tasks.is_cancelled(tid):
            continue
        tasks.set_login_wait(tid, False)
        tasks.finish(tid, "failed", message)


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
    """Is there ALREADY a session on `site`? Navigate headless and verify that it is NOT a login screen AND there is
    NO visible 'sign in' button (the site already shows your account). Avoids reopening login when already inside
    (bug 2026-07-10: resumed the search and reopened Wallapop login while already authenticated). Best-effort: if in
    doubt return False (better to check login than act without an account)."""
    if not site:
        return False
    from . import agent
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
    from . import agent
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
