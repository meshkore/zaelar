"""`TaskBrowser`: one task's own tab — opening it, capturing it, navigating, closing popups, closing it. Its
actions and its reads of the page are the mixins in `browser_steps` and `browser_page`. The owner's state and every
name are read through the package (`_o.<name>`), so a patch on `owner` governs every call.
"""

import asyncio
import re

from nucleo.errors import brief as _brief
from urllib.parse import quote_plus
from widgets import store

from widgets.navegador import owner as _o
from widgets.navegador.owner.browser_page import _PageMixin
from widgets.navegador.owner.browser_steps import _StepsMixin


class TaskBrowser(_StepsMixin, _PageMixin):
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.page = None
        self.mouse = {"x": 0.0, "y": 0.0}   # this tab's OWN mouse
        self.refs: dict = {}
        self.rev = 0

    async def ensure(self):
        if self.page is not None and not self.page.is_closed():
            return self.page
        await _o._ensure_page()                 # ensure the window (persistent context) + main tab
        self.page = await _o._context.new_page()   # new TAB in the SAME window
        # V2-358 — the HTTP STATUS of the page the tab stands on, kept fresh by the response stream (goto AND
        # click-driven navigations): the wall signal no body needle can miss (one 403, many block pages).
        # Main-frame document responses only.
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
        # V2-044: each navigation step is chained to the phrase that requested the task (no turn context in the
        # server loop → the trace lives in the task registry).
        if "trace" not in extra:
            try:
                from widgets.navegador import tasks as _tasks
                _tid = _tasks.trace_of(self.task_id)
                if _tid:
                    extra["trace"] = _tid
                    extra["span"] = f"web:{self.task_id}"
            except Exception:
                pass
        _o._emit(label, text, task=self.task_id, **extra)

    async def _capture(self) -> None:
        page = self.page
        shot = f"{store.data_dir(_o.WID)}/shot-{self.task_id}.png"
        async with _o._shot_lock:               # serialize captures across parallel tasks
            # NO bring_to_front: in headless (default) all tabs render; bringing it to front also stole the operator's
            # focus/cursor (they could not type on their computer). Playwright screenshots background tabs.
            await page.screenshot(path=shot, type="png", full_page=False)
        # OFF-LOOP (V2-035): move PIL cursor compositing to a thread → does not steal GIL from the TTS audio pump.
        await asyncio.to_thread(_o._draw_cursor, shot, self.mouse["x"], self.mouse["y"])
        self.rev += 1
        title = ""
        try:
            title = await page.title()
        except Exception:
            pass
        # V2-167 (second half): the tab is the ONLY place holding both URL and text, so the only one that can spot a
        # wall served in the BODY of an ordinary URL. Bounded and best-effort: a capture never fails for the text.
        from widgets.navegador import tasks
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
            await _o._dismiss_overlays(page)
            # ...and it records WHICH PAGE it was done for, so the look that follows does not sweep again just
            # because the URL has just changed.
            self._overlays_host = _o._host_of(getattr(page, "url", "") or url)
            await asyncio.sleep(0.35)
        except Exception as e:
            self._emit("nav_error", _brief(e, 160))
            return
        await self._capture()

    async def _reap_popups(self) -> None:
        """Avoid accumulating tabs: close popups (target=_blank) the site opens after a click. If the popup was the
        listing we meant to view, ABSORB its URL into OUR tab and close it. Never touches another task's tab."""
        try:
            ctx = self.page.context
        except Exception:
            return
        owned = {tb.page for tb in _o._task_browsers.values() if getattr(tb, "page", None)}
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
                await _o._dismiss_overlays(self.page)
                await asyncio.sleep(0.3)
            except Exception:
                pass

    async def open_target(self, raw: str) -> None:
        """Simple navigation (browse, no loop): open a URL/domain, or search if it is loose text, or YouTube."""
        raw = (raw or "").strip()
        if not raw:
            return
        yid = _o._youtube_id(raw)
        if yid:
            await self._goto(f"https://www.youtube.com/watch?v={yid}")
        elif _o._looks_like_url(raw):
            await self._goto(_o._normalize_url(raw))
        else:
            await self.search(raw)

    async def search(self, q: str) -> None:
        q = (q or "").strip()
        if q:
            await self._goto(_o._SEARCH_URL.replace("{q}", quote_plus(q)))

    async def open_youtube(self, q: str, url: str = "") -> None:
        yid = _o._youtube_id(url) or (url if re.fullmatch(r"[0-9A-Za-z_-]{11}", url or "") else "")
        if not yid and q:
            page = await self.ensure()
            try:
                await page.goto(f"https://www.youtube.com/results?search_query={quote_plus(q)}",
                                wait_until="domcontentloaded")
                await asyncio.sleep(0.5)
                m = _o._YT_ID_RE.search(await page.content())
                yid = m.group(1) if m else ""
            except Exception:
                pass
        await self._goto(f"https://www.youtube.com/watch?v={yid}" if yid
                         else f"https://www.youtube.com/results?search_query={quote_plus(q)}")

    async def close(self) -> None:
        try:
            if self.page and not self.page.is_closed():
                await self.page.close()
        except Exception:
            pass
        self.page = None
