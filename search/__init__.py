"""search/ — the SEARCH SERVICE: one door in, one result shape out (V2-782).

    from search import find
    res = find("fontanero urgente en Madrid, el mejor valorado")      # → SearchResult
    res.route, res.provider, res.candidates, res.pages, res.unshown, res.needs

What lives here and nowhere else:
  · `route.py`      — WHICH module serves a request (fact · listing · local service · images · browser · worker)
  · `criteria.py`   — what the request says about HOW MANY and WHICH data fields
  · `candidacy.py`  — a candidate vs the PAGE that lists candidates; the criterion no row can show
  · `result.py`     — the one shape every door returns, and the sheet rows it becomes
  · `web.py`        — the fact/lead chain (Perplexity → Tavily → Gemini → Z.ai → Brave → Chromium Google → DDG)
  · `listing.py` + `extract.py` — the listing ladder (SERP → HTTP + JSON-LD → unlocker) and its pure extractor
  · `browser.py`    — the warm Chromium (Google, and the image indexes); `images.py` — the pure image parsers
  · `providers/`    — every external index declared once: keys (names), kind, host, paid
  · `health.py`     — one minimal real call per provider: live · missing · exhausted · blocked · down
  · `api.py`        — the HTTP face (`/api/search/find`, `/api/search/health`, `/api/search/route`)

The direction is one-way: the turn (`nucleo/flash`), the workers and the sheet call this package; this package
never imports them. The seams it needs from its host are callables in `hooks.py`, set at boot. Standalone, with
no hooks set, everything here still works — that is what makes it a service and not a corner of the brain.

`find()` is BLOCKING (network): callers on an event loop use `asyncio.to_thread`. It never raises: a collapsed
chain is a `SearchResult` with `failure`, and a module the service cannot run itself (a browser session, a
brain worker) comes back as `needs`, for the caller to commission.
"""
from __future__ import annotations

import time

from . import candidacy as _candidacy
from . import criteria as _criteria
from . import hooks as _hooks
from .result import (BRAIN_WORKER, BROWSER, IMAGES, INLINE_FACT, LISTING, LOCAL_SERVICE, MODULES,  # noqa: F401
                     Candidate, Page, SearchResult, Source, candidate_from_row)
from .route import Route, search_route  # noqa: F401

__all__ = ["find", "search_route", "Route", "SearchResult", "Candidate", "Page", "Source", "MODULES",
           "INLINE_FACT", "LISTING", "LOCAL_SERVICE", "IMAGES", "BROWSER", "BRAIN_WORKER"]

#: How many leads a fact search keeps as candidates (the top of the chain's results), and how many a hunt reads.
_FACT_K = 5
_LEADS_K = 10


def _criteria_of(request: str, route: Route) -> dict:
    return {"hard": _criteria.hard_criteria(request), "fields": list(route.fields),
            "n_final": route.breadth.get("n_final"), "min_candidates": route.breadth.get("min_candidates")}


def _rows_from_web(res: dict, origin: str = "web") -> list[dict]:
    """The chain's `{title, snippet, url}` rows → sheet-shaped rows, with the ONE amount a title or snippet names
    as the price (V2-471: several amounts is ambiguity, nothing is guessed)."""
    rows = []
    for r in (res or {}).get("results") or []:
        if not isinstance(r, dict):
            continue
        title = " ".join(str(r.get("title") or "").split())
        if not title:
            continue
        row = {"title": title, "subtitle": " ".join(str(r.get("snippet") or "").split())[:160],
               "url": str(r.get("url") or "").strip(), "origin": origin}
        p = _candidacy.lone_amount(title) or _candidacy.lone_amount(row["subtitle"])
        if p:
            row["price"] = p
        # A phone a business wrote in its own title or snippet is ITS datum (measured 2026-10-10 on Z.ai leads:
        # «Fontaneros Urgentes en Madrid - 622 65 44 32»); the shape rule in `candidacy.lone_phone` keeps dates out.
        tel = _candidacy.lone_phone(title) or _candidacy.lone_phone(row["subtitle"])
        if tel:
            row["phone"] = tel
        rows.append(row)
    return rows


def _split(rows: list[dict], origin: str) -> tuple[list[Candidate], list[Page]]:
    keep, pages = _candidacy.split(rows)
    cands = [candidate_from_row(r, origin=r.get("origin") or origin) for r in keep]
    return cands, [Page(p["title"], p.get("url", ""), p["why"]) for p in pages]


def _fact(request: str, k: int, out: SearchResult) -> None:
    from . import web as _web
    res = _web.search(request, k=max(1, k), mode="answer")
    out.raw = res
    out.provider = str(res.get("source") or "")
    out.answer = str(res.get("answer") or "")
    out.failure = res.get("failure")
    out.repeated = res.get("repeated")
    out.candidates, out.pages = _split(_rows_from_web(res), "web")
    out.sources.append(Source(name=f"web search ({out.provider})", status="ok" if res.get("results") or res.get("answer")
                              else ("error" if out.failure else "empty"), found=len(res.get("results") or []),
                              note=str((out.failure or {}).get("detail") or "")[:160]))


def _leads(request: str, k: int, out: SearchResult, origin: str = "web") -> None:
    from . import web as _web
    res = _web.search(request, k=max(1, k), mode="results")
    out.raw = res
    out.provider = str(res.get("source") or "")
    out.failure = res.get("failure")
    out.candidates, out.pages = _split(_rows_from_web(res, origin), origin)
    out.sources.append(Source(name=f"web search ({out.provider})", status="ok" if res.get("results") else
                              ("error" if out.failure else "empty"), found=len(res.get("results") or []),
                              note=str((out.failure or {}).get("detail") or "")[:160]))


def _format_price(price, currency: str) -> str:
    if price is None:
        return ""
    try:
        f = float(price)
    except (TypeError, ValueError):
        return str(price)
    n = f"{f:,.0f}".replace(",", ".") if f == int(f) else f"{f:,.2f}"
    return f"{n} {currency}".strip() if currency else n


def _listing(request: str, k: int, out: SearchResult, *, price_max, price_min, condition, countries, deadline_s) -> None:
    from . import listing as _listing
    q = _listing.ListingQuery(text=request, countries=tuple(countries or ()), price_max=price_max, price_min=price_min,
                              condition=str(condition or ""), limit=max(k, 20), deadline_s=float(deadline_s or 0.0))
    res = _listing.search(q)
    rows = []
    for it in res.get("items") or []:
        attrs = it.get("attributes") or {}
        rows.append({"title": it.get("title", ""), "url": it.get("url", ""), "image": it.get("image", ""),
                     "price": _format_price(it.get("price"), str(it.get("currency") or "")),
                     "subtitle": " · ".join(str(b) for b in (it.get("location"), it.get("source")) if b),
                     "facts": [{"label": str(a), "value": str(v)} for a, v in list(attrs.items())[:6] if str(v).strip()],
                     "origin": "listing"})
    out.provider = "listing ladder" + (" (cached)" if res.get("cached") else "")
    out.candidates, out.pages = _split(rows, "listing")
    for s in res.get("sources") or []:
        out.sources.append(Source(name=f"{s.get('tier', '?')}: {s.get('target', '')}".strip(": "),
                                  status=str(s.get("status") or "ok"), note=str(s.get("note") or "")[:160],
                                  found=s.get("kept", s.get("n"))))
    if res.get("needs_browser"):
        out.needs = BROWSER
        out.sources.append(Source(name="listing ladder", status="empty", note=str(res.get("reason") or "")[:200]))


def _local(request: str, k: int, out: SearchResult, near: str) -> None:
    from .providers import foursquare as _fsq, keys as _keys
    if _keys.present("foursquare"):
        try:
            rows = _fsq.places(request, near=near, k=k)
            if rows:
                out.provider = "foursquare"
                out.candidates = [Candidate(title=r["title"], url=r.get("url", ""), subtitle=r.get("subtitle", ""),
                                            phone=r.get("phone", ""), rating=r.get("rating", ""),
                                            availability=r.get("availability", ""), origin="local") for r in rows]
                out.sources.append(Source(name="foursquare places", status="ok", found=len(rows)))
                return
            out.sources.append(Source(name="foursquare places", status="empty", found=0))
        except Exception as e:  # noqa: BLE001 — a dead directory falls back to the web chain, and says so
            out.sources.append(Source(name="foursquare places", status="error", note=str(e)[:160]))
    _leads(request, max(k, _LEADS_K), out, origin="web")


def _images(request: str, k: int, out: SearchResult) -> None:
    from . import browser as _browser
    try:
        res = _browser.images_sync(request, k=max(k, 6))
    except Exception as e:  # noqa: BLE001 — no warm Chromium (a standalone process): an honest empty result
        out.failure = {"kind": "unavailable", "detail": str(e)[:200]}
        out.sources.append(Source(name="image indexes", status="error", note=str(e)[:160]))
        return
    out.provider = str(res.get("source") or "")
    for it in (res.get("items") or [])[:k]:
        if not isinstance(it, dict):
            continue
        out.candidates.append(Candidate(title=str(it.get("title") or it.get("page_title") or request)[:160],
                                        url=str(it.get("page") or it.get("page_url") or it.get("url") or ""),
                                        image=str(it.get("url") or it.get("image") or ""), origin="images",
                                        subtitle=str(it.get("site") or it.get("source") or "")[:120]))
    if res.get("blocked"):
        out.failure = {"kind": "captcha", "detail": f"{res.get('degraded_from') or out.provider}: blocked"}
    out.sources.append(Source(name=f"image index ({out.provider})", status="blocked" if res.get("blocked") else "ok",
                              found=len(out.candidates)))


def find(request: str, *, route: str | Route | None = None, k: int = 8, price_max=None, price_min=None,
         condition: str = "", countries=(), near: str = "", deadline_s: float = 0.0,
         proposal: str = "", verdicts: dict | None = None, judge=None, named_site: bool = False) -> SearchResult:
    """The service's one door. See the package docstring. Never raises."""
    t0 = time.monotonic()
    text = " ".join(str(request or "").split())
    if isinstance(route, Route):
        rt = route
    elif isinstance(route, str) and route in MODULES:
        rt = search_route(text, proposal=proposal, verdicts={**(verdicts or {}), "search_module": (route, 1.0)},
                          named_site=named_site)
    else:
        rt = search_route(text, proposal=proposal, verdicts=verdicts, judge=judge, named_site=named_site)
    out = SearchResult(query=text, route=rt.module, criteria=_criteria_of(text, rt))
    if not text:
        out.failure = {"kind": "empty", "detail": "empty request"}
        return out
    try:
        if rt.module == INLINE_FACT:
            _fact(text, max(k, _FACT_K), out)
        elif rt.module == LISTING:
            _listing(text, k, out, price_max=price_max, price_min=price_min, condition=condition,
                     countries=countries, deadline_s=deadline_s)
        elif rt.module == LOCAL_SERVICE:
            _local(text, k, out, near)
        elif rt.module == IMAGES:
            _images(text, k, out)
        else:
            out.needs = rt.module          # browser · brain_worker: the caller commissions it
    except Exception as e:  # noqa: BLE001 — the service answers with a failure, it never takes the caller down
        out.failure = {"kind": "error", "detail": f"{type(e).__name__}: {str(e)[:160]}"}
    rows = [c.to_row() for c in out.candidates]
    out.unshown = _candidacy.unshown_criteria(rows, {"hard": out.criteria.get("hard") or []}) if rows else []
    out.took_ms = int((time.monotonic() - t0) * 1000)
    _hooks.note("search", "🧭 servicio de búsqueda", role="system", text=text[:160],
                extra={"route": rt.module, "why": rt.why, "provider": out.provider, "n": len(out.candidates),
                       "pages": len(out.pages), "needs": out.needs, "ms": out.took_ms,
                       **({"failure": out.failure} if out.failure else {})})
    return out
