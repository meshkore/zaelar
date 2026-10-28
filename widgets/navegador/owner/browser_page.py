"""`TaskBrowser`'s reads of the page (`_PageMixin`): the snapshot for the agent, a screenshot, the listings of
a results grid, and a card read in its own tab.
Moved out of `owner.py`; the owner's state and every module name are read through the package (`_o.<name>`), so a
patch on `owner` still governs every call.
"""

import asyncio

from nucleo.errors import brief as _brief

from widgets.navegador import owner as _o


class _PageMixin:
    """`TaskBrowser`'s reads of the page: the snapshot for the agent, a screenshot, the listings, a visited card."""

    async def snapshot_for_agent(self) -> dict:
        page = await self.ensure()
        # THE BANNER BELONGS TO NAVIGATION, NOT TO EACH LOOK. `_dismiss_overlays` waits 2.5 s for a known CMP
        # to appear and, if it does not, sweeps ALL frames × ALL selectors — and a site with ad iframes has many
        # frames. That full cost was paid on every `look`. Measured on the live es.wallapop.com setup, same page
        # and no banner: 11.17 · 11.23 · 11.45 s, three consecutive looks. It is not the cost of accepting
        # cookies once, but a fixed toll per action — and with the operator asking the worker to open tabs and
        # assess listings one by one, that toll is the ceiling.
        # Sweep when CHANGING pages, when a new banner may exist. If one appears late on the same URL, it appears
        # in the capture and the worker can click it: one automation is lost, not the result.
        _h = _o._host_of(getattr(page, "url", "") or "")
        if _h != getattr(self, "_overlays_host", None):
            await _o._dismiss_overlays(page)
            self._overlays_host = _h
        self.refs = {}
        # V2-248 — WHERE this look was taken. Stored so an expired `ref` can explain why it expired: if the page
        # is no longer the same, the reason is not that the number was written incorrectly.
        self.refs_url = getattr(page, "url", "") or ""
        # EACH DOM READ, BOUNDED. None of the three was: `query_selector_all` and `title()` hit the context's
        # default timeout and `evaluate` HAS NONE. And the costly part is not waiting, but what waiting TURNS
        # INTO: the action had already worked —the text had been entered— and the worker received "the browser
        # did not respond to type", that is, a failure, and repeated it. Here, whatever is available is returned,
        # SAYING that the view is incomplete, instead of bringing down an action that succeeded.
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
            # NAME what there was not time to read and say what to do, instead of presenting a partial view as
            # though it were the whole page —which is how a worker concludes "there is nothing here" about a
            # full listing. Same contract as node 4.20: the bridge says what it knows.
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

        Operator request (2026-08-24): «the brain worker itself must extract data, model the different listings,
        open enough tabs to investigate, and assess each result listing». It could not do that before: the bridge
        only knew `navigate`, which takes over the ONLY tab —so inspecting one listing meant losing the results and
        searching for it again, two 7-11 s navigations per listing, with the search and filters in between.

        It returns what is needed to ASSESS a listing: its title, truncated listing text, and the listings declared
        by the page itself (price, image). Not a capture: assessing ten listings by vision means ten PNG reads,
        and this must be possible many times.

        The tab is ALWAYS closed, including if reading fails —one orphaned tab per listing is how it reaches the
        thirty already measured by `_reap_popups`. And `self.page` is untouched on every path: the results remain
        where they were, which is the reason this verb exists.
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
                # THE CONTENT, NOT THE MENU. `body.innerText` starts with navigation chrome —measured in the first
                # test: «Todas las categorías Coches Motos Motor y accesorios…»— and with truncated text that
                # leaves the worker assessing a listing by the site's menu. It is the same pattern V2-234 measured
                # during extraction, through the other entry point.
                #
                # The rule is STRUCTURAL, not a site list: if the page declares its main content (`main`, `article`,
                # `[role=main]`), read that; otherwise read the entire body, which is what existed. Do not truncate
                # by position or guess where the menu ends.
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
