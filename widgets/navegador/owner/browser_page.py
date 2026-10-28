"""`TaskBrowser`'s reads of the page (`_PageMixin`): the snapshot for the agent, a screenshot, the listings of
a results grid, and a card read in its own tab. The owner's state and every name are read through the package
(`_o.<name>`), so a patch on `owner` governs every call.
"""

import asyncio

from nucleo.errors import brief as _brief

from widgets.navegador import owner as _o


class _PageMixin:
    """`TaskBrowser`'s reads of the page: the snapshot for the agent, a screenshot, the listings, a visited card."""

    async def snapshot_for_agent(self) -> dict:
        page = await self.ensure()
        # THE BANNER BELONGS TO NAVIGATION, NOT TO EACH LOOK: `_dismiss_overlays` (wait for a CMP, then sweep all
        # frames × selectors) is a fixed toll of seconds. Sweep when CHANGING pages; a late banner on the same URL
        # shows in the capture and the worker can click it.
        _h = _o._host_of(getattr(page, "url", "") or "")
        if _h != getattr(self, "_overlays_host", None):
            await _o._dismiss_overlays(page)
            self._overlays_host = _h
        self.refs = {}
        # V2-248 — WHERE this look was taken, so an expired `ref` can say whether the page changed under it.
        self.refs_url = getattr(page, "url", "") or ""
        # EACH DOM READ, BOUNDED (`evaluate` has no timeout of its own): an action that already worked must not
        # come back as a failure. Whatever is available is returned, SAYING the view is incomplete.
        _slow = []
        try:
            handles = await asyncio.wait_for(page.query_selector_all(_o._INTERACTIVE), _o._DOM_TIMEOUT_S)
        except Exception:
            handles, _ = [], _slow.append("elementos")
        try:
            metas = await asyncio.wait_for(_o._bulk_metas(page), _o._DOM_TIMEOUT_S)
        except Exception:
            metas, _ = {}, _slow.append("etiquetas")
        lines = _o._snapshot_lines(handles, metas, self.refs)
        title = ""
        try:
            title = await asyncio.wait_for(page.title(), _o._DOM_TIMEOUT_S)
        except Exception:
            _slow.append("título")
        out = {"url": page.url, "title": title or "", "elements": "\n".join(lines)}
        if _slow:
            # NAME what there was no time to read and what to do, instead of passing a partial view off as the
            # whole page (node 4.20: the bridge says what it knows).
            out["partial"] = ", ".join(_slow)
            out["note"] = (f"la página seguía cargando y no dio tiempo a leer: {out['partial']}. "
                           f"La acción SÍ se hizo. Vuelve a mirar con «look» antes de decidir nada.")
        return out

    async def screenshot_b64(self) -> str:
        import base64
        page = await self.ensure()
        png = await page.screenshot(type="png", full_page=False)
        return base64.b64encode(png).decode()

    async def extract_listings(self, limit: int = 14) -> list:
        """Scrape the CURRENT page for 'listings'/results: links with image and/or price (generic — Wallapop,
        Idealista, stores). Returns [{title, price, url, image}]. Does not raise."""
        try:
            return await self.page.evaluate(_o._JS_EXTRACT, limit) or []
        except Exception:
            return []

    async def visit(self, url: str, chars: int = 2500) -> dict:
        """Open a listing in ANOTHER tab, read it, and close it — without moving the listing tab.

        It returns what ASSESSING a listing needs (title, truncated main text, the page's own declared listings),
        not a capture, so it can run many times. The tab is ALWAYS closed, even if reading fails, and `self.page`
        is untouched on every path: the results stay where they were, which is why this verb exists.
        """
        page = await self.ensure()
        try:
            ctx = page.context
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": _brief(e, 120)}
        tab = None
        try:
            tab = await ctx.new_page()
            await tab.goto(_o._normalize_url(url), wait_until="domcontentloaded")
            # No banner sweep: the listing is read, not driven, and the sweep is the toll just removed from the
            # hot path. A banner covers the view, not the text.
            title, body, items = "", "", []
            try:
                title = await asyncio.wait_for(tab.title(), _o._DOM_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
            try:
                # THE CONTENT, NOT THE MENU (`body.innerText` starts with navigation chrome, cf. V2-234). The rule
                # is STRUCTURAL, not a site list: read the declared main content (`main`, `article`,
                # `[role=main]`) if there is one, else the whole body; never truncate by guessing where a menu ends.
                body = await asyncio.wait_for(tab.evaluate(
                    "() => { const m = document.querySelector('main, article, [role=main]');"
                    "        return ((m || document.body || {}).innerText) || ''; }"), _o._DOM_TIMEOUT_S)
            except Exception:  # noqa: BLE001
                pass
            try:
                items = await asyncio.wait_for(tab.evaluate(_o._JS_EXTRACT, 6), _o._DOM_TIMEOUT_S) or []
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
