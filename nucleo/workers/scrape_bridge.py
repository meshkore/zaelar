"""nucleo/workers/scrape_bridge.py — a worker's `use_tool: scrape`: reading a page through `scrape.read` (V2-846 F6).

The one road a worker has to READ a page. Its built-in WebFetch is gone from every allowlist: it fetched from this
machine with no unlocker, read the page with the CLI's own small model, and left no row for the meter or the audit.
Here the page comes through the fetch ladder, its listings through the extraction ladder and the one validator, and
everything the page says comes back FENCED as a third party's text (`nucleo/untrusted`).
"""
from __future__ import annotations

import asyncio

#: Records handed back to the worker at most (a listings page holds 20-40; the sheet takes the rest by its own door).
_MAX_RECORDS = 40


async def run(payload: dict, rec) -> dict:
    """The page the worker asked to read: its records, or its readable text when it has none. Never raises."""
    args = payload.get("args") or {}
    url = str(args.get("url") or payload.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "falta `url`: una dirección absoluta (https://…). Para buscar sin dirección, "
                                      "`act use_tool \"<qué buscas>\"`."}
    try:
        import scrape
        from nucleo import untrusted as _u
        res = await asyncio.to_thread(scrape.read, url, str(args.get("want") or "listings"))
        out = res.to_dict()
        out["records"] = out["records"][:_MAX_RECORDS]
        if not out["records"] and res.html:
            from scrape import markup
            out["text"] = markup.readable(res.html, url, limit=8000)
        return {"ok": res.ok() or bool(out.get("text")), "result": _u.fence_tree(out)}
    except Exception as e:  # noqa: BLE001 — a read that broke is said to the worker, never raised into it
        return {"ok": False, "error": f"scrape falló: {type(e).__name__}: {str(e)[:160]}"}
