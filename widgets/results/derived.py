"""widgets/results/derived.py — the fields of a sheet that are COMPUTED, never stored: `_counts` and
`_identity` are derived on every read, and `_save` strips every derived field before it persists.
`data` re-exports the three names.
"""
from .. import store
from .sheet_names import sheet_key


def _counts(data: dict) -> dict:
    """DERIVED counts, kept apart from reported ones: only the worker knows how many it explored; the sheet knows
    what is on screen. If nobody reported breadth, the summary SAYS so instead of passing the card count off as it."""
    items = data.get("items") or []
    sources = data.get("sources") or []
    summary = data.get("summary") or {}
    ok = [s for s in sources if s.get("status") in ("ok", "partial")]
    got = sum(int(s.get("found") or 0) for s in sources)
    return {
        "shown": len(items),
        "sources": len(sources),
        "sources_ok": len(ok),
        "sources_failed": len([s for s in sources if s.get("status") in ("auth", "blocked", "error")]),
        "from_sources": got,                     # candidates seen ACCORDING TO reported sources
        "explored": summary.get("explored"),     # what the worker declares to have truly evaluated
        "selected": summary.get("selected", len(items) or None),
    }


def _identity() -> dict:
    """Install + session ids for the SUMMARY tab's audit strip, served IN the payload because widget.js may not
    fetch (V2-538, V2-601 T-10). Fail-open to {}: no identity, no strip. The engine import is why `results` is in
    the validator's `_STDLIB_EXEMPT`."""
    try:
        from observability import identity as _ident
        info = _ident.session_info() or {}
        return {"user_id": str(_ident.user_id() or ""), "session_id": str(info.get("id") or "")}
    except Exception:  # noqa: BLE001
        return {}


def _save(data: dict, sheet: str = "") -> None:
    """Persist WITHOUT derived fields: `counts` is recalculated on read, and storing it would make it stale as soon as
    anything else changes (an old number on screen is worse than no number)."""
    d = dict(data)
    d.pop("counts", None)
    d.pop("progress", None)                  # derived from the live record: storing it would freeze a «Trabajando…»
    d.pop("browser", None)                   # derived too (V2-571): a stored capture would outlive its browser
    d.pop("identity", None)                  # derived every read (T-10): ids belong to the PROCESS, not the sheet
    for k in ("sources", "summary", "criteria"):
        if not d.get(k):
            d.pop(k, None)                       # remove empty sections: the blank sheet remains blank
    store.save(sheet_key(sheet), d)
