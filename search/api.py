"""search/api.py — the HTTP face of the search service (V2-782 T5.2).

    GET  /api/search/health[?fresh=1]   → {providers:[…], summary:{…}}   (cached 120 s; includes the Chromium)
    POST /api/search/find   {query, route?, k?, price_max?, price_min?, condition?, countries?, near?}
                                         → SearchResult.to_dict()
    POST /api/search/route  {query, proposal?, verdicts?}  → the Route alone, no network

One door for the turn, the worker (through its bridge), a MeshKore agent and the operator's own curl — so the
same code can later run as its own process behind the same paths. Guarded like every `/api/*` route by
`server/api_guard.py` (loopback or token). Blocking work runs in a thread: the browser bridge needs the loop free.
"""
from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Body

router = APIRouter()

_HEALTH_TTL_S = 120.0
_health_cache: dict = {"at": 0.0, "rows": []}


@router.get("/api/search/health")
async def health(fresh: int = 0):
    from . import health as _health
    now = time.time()
    if fresh or not _health_cache["rows"] or now - _health_cache["at"] > _HEALTH_TTL_S:
        rows = await asyncio.to_thread(_health.probe_all)
        _health_cache.update(at=time.time(), rows=rows)
    rows = _health_cache["rows"]
    return {"providers": rows, "summary": _health.summary(rows), "cached_s": int(time.time() - _health_cache["at"])}


@router.post("/api/search/find")
async def find(body: dict = Body(...)):
    from . import find as _find
    b = body if isinstance(body, dict) else {}
    kw = {k: b.get(k) for k in ("price_max", "price_min") if b.get(k) is not None}
    res = await asyncio.to_thread(
        _find, str(b.get("query") or ""), route=b.get("route") or None, k=int(b.get("k") or 8),
        condition=str(b.get("condition") or ""), countries=tuple(b.get("countries") or ()),
        near=str(b.get("near") or ""), deadline_s=float(b.get("deadline_s") or 0.0),
        proposal=str(b.get("proposal") or ""), verdicts=b.get("verdicts") if isinstance(b.get("verdicts"), dict) else None,
        named_site=bool(b.get("named_site")), **kw)
    return res.to_dict()


@router.post("/api/search/route")
async def route(body: dict = Body(...)):
    from .route import search_route
    b = body if isinstance(body, dict) else {}
    rt = search_route(str(b.get("query") or ""), proposal=str(b.get("proposal") or ""),
                      verdicts=b.get("verdicts") if isinstance(b.get("verdicts"), dict) else None,
                      named_site=bool(b.get("named_site")))
    return rt.to_dict()
