"""The owner's mailbox (`handle`), the cookie/consent banner it clears after each navigation, and the reason an
expired element ref gives. The owner's state and every name are read through the package (`_o.<name>`), so a
patch on `owner` governs every call.
"""

import asyncio

from loguru import logger

from widgets.navegador import owner as _o


def _host_of(url: str) -> str:
    """The DOMAIN of a URL — the granularity at which cookie consent exists. A CMP accepted on a domain does not
    reappear while moving within it, and keying by URL made every `type --submit` (new URL) sweep again."""
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
        combined = ", ".join(_o._CMP_ACCEPT)
        btn = await page.wait_for_selector(combined, timeout=2500, state="visible")
        if btn:
            await btn.click(timeout=2000)
            _o._emit("dismiss_overlay", "cmp-accept")
            # WAIT until the banner is fully CLOSED before returning, or the screenshot still shows it.
            try:
                await page.wait_for_selector(combined, state="hidden", timeout=2500)
            except Exception:
                await asyncio.sleep(1.0)
            return
    except Exception:
        pass
    # 2) Text/generic-selector fallback, in ALL frames (some CMPs live in an iframe), without waits.
    # ONE query per frame (the selectors combined, as step 1 does), not one PER SELECTOR: a results page with ad
    # iframes has many frames, and N × M round trips cost seconds.
    _combined = ", ".join(_o._COOKIE_SELECTORS)
    for fr in page.frames:
        try:
            btn = await fr.query_selector(_combined)
            if btn and await btn.is_visible():
                await btn.click(timeout=2000)
                await asyncio.sleep(0.3)
                _o._emit("dismiss_overlay", "fallback")
                return
        except Exception:
            continue


# ── mailbox commands ────────────────────────────────────────────────────────────────────────────────────────
async def handle(action: str, payload: dict) -> None:
    payload = payload or {}
    if action == "open":
        raw = str(payload.get("url") or "").strip()
        if not raw:
            return
        yid = _o._youtube_id(raw)
        if yid:
            await _o._show_youtube(yid, "")
        elif _o._looks_like_url(raw):
            await _o._goto(_o._normalize_url(raw))
        else:
            await _o._search(raw)                        # loose text in the bar → web search
    elif action == "search":
        await _o._search(str(payload.get("q") or payload.get("url") or "").strip())
    elif action == "youtube":
        await _o._youtube(str(payload.get("q") or "").strip(), str(payload.get("url") or "").strip())
    elif action in ("back", "forward"):
        await _o._step(action)
    elif action == "reload":
        page = await _o._ensure_page()
        _o._write(loading=True)
        try:
            await page.reload(wait_until="domcontentloaded")
            await _o._dismiss_overlays(page)
            await asyncio.sleep(0.3)
        except Exception:
            pass
        await _o._capture()
    elif action == "scroll":
        await _o._scroll(float(payload.get("dy") or 0))
    elif action == "click":
        await _o._click(float(payload.get("x") or 0), float(payload.get("y") or 0))
    elif action == "type":
        await _o._type(str(payload.get("text") or ""))
    elif action == "press":
        await _o._press(str(payload.get("key") or ""))
    elif action in ("close", "quit", "close_browser"):
        await _o._close_browser()
    elif action == "automate":
        # SPAWN (no await): the owner's mailbox is SERIAL — if we waited for the whole loop, tasks would not run in
        # PARALLEL. Launch the task in the background and free the mailbox for the next command → N concurrent tasks,
        # each in its own tab. Keep the ref so GC does not collect it.
        _t = asyncio.create_task(_o._automate(str(payload.get("goal") or payload.get("task") or ""),
                                           str(payload.get("plan") or ""), str(payload.get("task_id") or "")))
        _o._running.add(_t)
        _t.add_done_callback(_o._running.discard)
    elif action == "browse":
        # SIMPLE navigation for a task/tab (no loop): open/search/youtube in ITS tab → vertical card.
        _t = asyncio.create_task(_o._browse(str(payload.get("task_id") or ""), str(payload.get("mode") or "open"),
                                         str(payload.get("url") or ""), str(payload.get("q") or "")))
        _o._running.add(_t)
        _t.add_done_callback(_o._running.discard)
    elif action == "authenticate":
        await _o._authenticate(str(payload.get("task_id") or ""), str(payload.get("url") or ""))
    elif action == "auth_done":
        await _o._auth_done(str(payload.get("task_id") or ""))
    elif action == "cancel_task":
        await _o._close_task(str(payload.get("task_id") or ""))
    elif action == "answer_task":
        from widgets.navegador import tasks
        tasks.answer(str(payload.get("task_id") or ""), str(payload.get("text") or ""))
    else:
        logger.debug(f"navegador: orden desconocida {action!r}")


# ── TaskBrowser: ONE TAB dedicated to a task ─────────────────────────────────────────────────────────────────
# Its page + mouse + refs behind the SAME interface agent.py expects from `owner` (snapshot_for_agent / agent_act /
# screenshot_b64 / _emit), so it drives ITS tab without touching the main tab. task ↔ tab ↔ canvas card, 1:1, all
# in the SAME window (shared persistent context).
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
