"""The browser's ACTIONS: the web task agent (`_automate`), plain browsing, and the page gestures the operator and
the agent drive — search, step, scroll, click, type, press — plus the YouTube exception (V2-778 F1, 2026-10-01).

Moved out of `widgets/navegador/owner.py` with no behaviour change. Every module-level name these functions read —
each other included — is read through the owner (`_o.<name>`), so a patch on `owner` still governs every call, and
the owner imports them back under their names.
"""
from __future__ import annotations

from widgets.navegador import owner as _o


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
    tb = _o.TaskBrowser(task_id)
    _o._task_browsers[task_id] = tb
    # ROBUSTNESS (V2-035): if the plan includes an already FILTERED results URL (first line `URL: …`, composed by the
    # planner from refined keywords + price), start the browser DIRECTLY on the results grid instead of typing into the
    # search box and navigating manually (the fragile path that got stuck on Wallapop). The rest of the plan remains
    # the loop guide.
    start_url = ""
    if plan:
        _m = _o.re.match(r"\s*URL:\s*(\S+)", plan, _o.re.I)
        if _m:
            start_url = _m.group(1).strip()
            plan = plan[_m.end():].lstrip("\n ")
    if start_url:
        try:
            tasks.milestone(task_id, "➡️ voy directo a la rejilla de resultados filtrada")
            await tb.agent_act("navigate", {"url": start_url})
        except Exception as e:  # noqa: BLE001
            _o.logger.warning(f"navegador: navigate inicial a resultados falló: {e}")
    try:
        res = await agent.run_task(goal, tb, plan=plan)
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "summary": f"error del automatizador: {_o._brief(e, 160)}"}
    # LOGIN WALL: the loop hit a sign-in page and did NOT type credentials. Open the real window so the operator can
    # sign in manually; the task is NOT closed — it remains paused and resumes by itself after auth_done.
    if res.get("needs_login"):
        await _o._begin_login(task_id, res.get("site", ""), res.get("login_url", ""), goal, plan)
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
            _o.logger.warning(f"extracción de resultados falló: {e}")
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
    tb = _o._task_browsers.get(task_id) or _o.TaskBrowser(task_id)
    _o._task_browsers[task_id] = tb
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
        tasks.milestone(task_id, f"⚠️ {_o._brief(e, 120)}")
    tasks.set_status(task_id, "open")
    tasks.set_phase(task_id, "abierto", False)


async def _close_task(task_id: str) -> None:
    """Close a task tab and mark it cancelled (when closing its card or by operator command)."""
    from . import tasks
    tb = _o._task_browsers.pop(task_id, None)
    if tb:
        await tb.close()
    if not tasks.is_cancelled(task_id) and tasks.get(task_id).get("status") in ("queued", "working", "needs_input"):
        tasks.cancel(task_id)


async def _search(q: str) -> None:
    if not q:
        return
    await _o._goto(_o._SEARCH_URL.replace("{q}", _o.quote_plus(q)))


async def _step(direction: str) -> None:
    page = await _o._ensure_page()
    _o._write(loading=True)
    try:
        if direction == "back":
            await page.go_back(wait_until="domcontentloaded")
            _o._idx = max(0, _o._idx - 1)
        else:
            await page.go_forward(wait_until="domcontentloaded")
            _o._idx = min(len(_o._hist) - 1, _o._idx + 1)
        await _o.asyncio.sleep(0.3)
    except Exception:
        pass
    await _o._capture()


async def _scroll(dy: float) -> None:
    page = await _o._ensure_page()
    try:
        await page.mouse.wheel(0, dy)
        await _o.asyncio.sleep(0.2)
    except Exception:
        pass
    await _o._capture()


async def _click(x: float, y: float) -> None:
    page = await _o._ensure_page()
    _o._write(loading=True)
    _o._emit("click", f"{int(x)},{int(y)}")
    try:
        await page.mouse.click(x, y)
        await _o.asyncio.sleep(0.6)                       # let a navigating click settle
    except Exception as e:
        _o._write(loading=False, error=f"No pude hacer clic: {_o._brief(e, 160)}")
        return
    if page.url and (not _o._hist or page.url != _o._hist[_o._idx if 0 <= _o._idx < len(_o._hist) else -1]):
        _o._hist = _o._hist[:_o._idx + 1] + [page.url]          # a click that navigated pushes to history
        _o._idx = len(_o._hist) - 1
    await _o._capture()


async def _type(text: str) -> None:
    page = await _o._ensure_page()
    try:
        await page.keyboard.type(text, delay=15)
    except Exception:
        pass
    await _o._capture()


async def _press(key: str) -> None:
    page = await _o._ensure_page()
    _o._write(loading=True)
    try:
        await page.keyboard.press(key or "Enter")
        await _o.asyncio.sleep(0.6)
    except Exception:
        pass
    await _o._capture()


# ── YouTube (embedded player, not screenshot) ────────────────────────────────────────────────────────────────
async def _youtube(q: str, url: str) -> None:
    yid = _o._youtube_id(url) or (url if _o.re.fullmatch(r"[0-9A-Za-z_-]{11}", url or "") else "")
    if yid:
        await _o._show_youtube(yid, "")
        return
    if not q:
        return
    # Resolve the first search video with Chromium (no API key): scrape "videoId" from the results HTML.
    page = await _o._ensure_page()
    _o._write(loading=True, error="")
    _o._emit("yt_search", q)
    try:
        await page.goto(f"https://www.youtube.com/results?search_query={_o.quote_plus(q)}",
                        wait_until="domcontentloaded")
        await _o._dismiss_overlays(page)
        await _o.asyncio.sleep(0.5)
        html = await page.content()
    except Exception as e:
        _o._write(loading=False, error=f"No pude buscar en YouTube: {str(e)[:160]}")
        return
    m = _o._YT_ID_RE.search(html)
    if m:
        await _o._show_youtube(m.group(1), q)
    else:
        await _o._capture()                               # no id → at least show the results as a page


async def _show_youtube(video_id: str, title: str) -> None:
    url = f"https://www.youtube.com/watch?v={video_id}"
    _o._hist = _o._hist[:_o._idx + 1] + [url]
    _o._idx = len(_o._hist) - 1
    _o._write(mode="youtube", url=url, title=title or "YouTube", youtube_id=video_id,
           youtube_title=title, loading=False, error="")
    _o._emit("youtube", video_id, title=title)
