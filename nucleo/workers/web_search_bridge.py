"""nucleo/workers/web_search_bridge.py — a worker's `use_tool: web_search`, through the search SERVICE (V2-782).

Extracted from `worker_api._exec_allow` (audit V2-783, plan item 9) when the per-errand search budget was added:
that function was already past the size ratchet's ceiling, and the budget belongs with the bridge it bounds.
"""
from __future__ import annotations

import asyncio


async def run(payload: dict, rec) -> dict:
    """The search the worker asked for, its rows handed to the conversation and the sheet. Never raises."""
    # V2-644 — the query key is forgiving, but an EMPTY query refuses loudly. Measured 2026-09-09: a worker
    # sent its query under another key, got back `{"results": [], "source": "none"}` twice, concluded «the
    # search bridge returns nothing» and drove the browser for four minutes. The silent echo blamed the
    # module; the real fault was the payload shape, which only an error naming the key could have said.
    args = payload.get("args") or {}
    q = ""
    for key in ("query", "q", "text", "search", "consulta"):
        q = str(args.get(key) or payload.get(key) or "").strip()
        if q:
            break
    if not q:
        return {"ok": False, "error": "falta `query`: la búsqueda va en "
                                      "{\"tool\":\"web_search\",\"args\":{\"query\":\"…\"}} — no adivino "
                                      "qué buscar con una query vacía."}
    from nucleo.workers import search_budget as _budget
    if (_spent := _budget.spend(getattr(rec, "task_id", ""))):
        return {"ok": False, "error": _spent}
    try:
        # V2-782 — through the SERVICE (route, candidates vs pages, what no row shows); `raw` = the chain's dict.
        from search import find as _find
        from nucleo.picture_errand import search_route as _route_of   # a picture errand searches IMAGES
        _sr = await asyncio.to_thread(_find, str(q), route=_route_of(rec), proposal="web_search",
                                      k=int((args.get("k") or payload.get("k") or 6)), market=market_words(rec))
        res = dict(_sr.raw or {"query": q, "answer": "", "results": [], "source": "none"})
        res.update({"route": _sr.route, "candidates": _sr.rows(), "pages": [{"title": p.title, "url": p.url,
                    "why": p.why} for p in _sr.pages], "unshown": list(_sr.unshown),
                    **({"failure": _sr.failure} if _sr.failure and not res.get("failure") else {})})
        # V2-236: and what the search brings goes INTO THE CONVERSATION immediately, not when the worker delivers
        # it — which failed to happen in 5 of 8 measured sessions. Same remedy V2-223 gave to what the browser
        # extracts through the other gate: this is OUR search, lent to the worker.
        try:
            from nucleo.workers import findings
            findings.hand_web_finding(getattr(rec, "task_id", ""), findings.render_search(res),
                                      getattr(rec, "goal", ""))
            # V2-320 — …and INTO THE SHEET, where the operator looks. A worker that solves by searching (without
            # a browser) ALWAYS left the sheet empty: the return only had a path to the note. Same gate as
            # the browser (V2-257) and the same rows carried by the note.
            findings.hand_search_rows(rec, res)
        except Exception:  # noqa: BLE001 — the search answered; a hand-off that failed is said, never fatal
            __import__("logging").getLogger("zaelar.worker").warning("web_search rows not handed on", exc_info=True)
        # V2-846 F6 (audit N3) — what the web said is a third party's text: fenced before the worker reads it, as
        # `mesh` and `scrape` do. The sheet and the conversation took their rows above, unfenced, as data.
        from nucleo import untrusted as _u
        return {"ok": True, "result": _u.fence_tree(res)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"web_search falló: {e}"}


def market_words(rec) -> str:
    """The errand's market — its brief's country and category (V2-840 H3) — for discovery. "" without a brief."""
    try:
        from nucleo.circuit import breadth as _breadth
        mk = (_breadth.brief_of(rec) or {}).get("market") or {}
        return " ".join(str(mk[k]) for k in ("country", "category") if mk.get(k))
    except Exception as e:  # noqa: BLE001 — a search never dies for its market words
        __import__("logging").getLogger("zaelar.worker").debug("web_search: no market words (%r)", e)
        return ""
