"""The browser's login ceremony: reaching a site's login page and opening the window the operator signs in
through (here, on a connected daemon, or blocked when no window can reach him)."""
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
    from widgets.navegador import agent
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
    from widgets.navegador import agent, auth_memory, tasks
    url = (url or "wallapop.com").strip()
    site = (site or _o._login_site_of(url)).strip().lower()
    if not task_id:
        task_id = tasks.create(f"Iniciar sesión · {site or url}", title=f"Login · {site or url}")
    _o._auth_resume.setdefault(task_id, {"goal": goal, "plan": plan, "site": site})
    # GUARD: a session ALREADY there → open no login; confirm it and continue the task (headless check, no window).
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
    # V2-822 — WHERE his window can open has one answer (`nucleo/browser_window.py`): here with a display, else on his
    # computer through a connected daemon that declares it can; otherwise nowhere, and the process is BLOCKED with
    # that state instead of waiting for a window that cannot exist.
    from nucleo import browser_window
    reach = browser_window.reach()
    if not reach:
        await _block_for_no_window(task_id, site or url)
        return
    if reach == browser_window.DAEMON:
        await _authenticate_on_daemon(task_id, url, site)
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


async def _block_for_no_window(task_id: str, site: str) -> None:
    """No window can reach him (no display here, no daemon connected that can open one): the task that needs his
    sign-in and the tasks paused behind it are BLOCKED — a live state, not a failure. Their entry in the processes
    panel says why, and he is told once, in his language, in the chat and by voice."""
    from widgets.navegador import tasks
    for tid in [task_id, *[t for t in list(_o._auth_resume) if t != task_id]]:
        if not tid or tasks.is_cancelled(tid):
            continue
        tasks.set_login_wait(tid, False, blocked="no_window")
    _o._auth_resume.clear()
    tasks.milestone(task_id, f"⛔ {site}: hace falta iniciar sesión y aquí no hay ventana — bloqueada")
    try:
        from voice import proactive
        await proactive.notify("navegador", _o._say().login_needs_daemon.replace("{site}", str(site)), speak=True)
    except Exception:
        pass


async def _authenticate_on_daemon(task_id: str, url: str, site: str) -> None:
    """The window opens on his computer through the connected daemon; this task waits for his sign-in there. The
    daemon's side reports it done through the same `auth_done` a local window ends with."""
    from nucleo import browser_window
    from widgets.navegador import tasks
    _o._auth_active = site
    tasks.set_status(task_id, "needs_input")
    tasks.set_phase(task_id, "esperando tu inicio de sesión", True)
    if not await browser_window.open_on_daemon(url, task_id):
        await _block_for_no_window(task_id, site or url)
        return
    tasks.set_login_wait(task_id, True)
    try:
        from voice import proactive
        await proactive.notify("navegador", _o._say().login_opened, speak=True)
    except Exception:
        pass


async def _begin_login(task_id: str, site: str, login_url: str, goal: str = "", plan: str = "") -> None:
    """A login wall stopped a task. PAUSE the other active tasks (one window → headed relaunch kills their tabs), record
    them for resumption, and open the login window (which watches itself). They resume in auth_done."""
    from widgets.navegador import tasks
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
