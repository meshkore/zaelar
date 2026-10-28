"""widgets/results/derived.py — the fields of a sheet that are COMPUTED, never stored: `_counts` and
`_identity` are derived on every read, and `_save` strips every derived field before it persists.

Moved byte for byte out of `widgets/results/data.py` (refactor2710-12); `data` re-exports the three names.
"""
from .. import store
from .sheet_names import sheet_key


def _counts(data: dict) -> dict:
    """DERIVED counts, intentionally separate from reported ones. "How many were explored" is only known by the
    worker (reported in summary); "how many are on screen" and "how many sources" are known by the sheet. Mixing them
    into one number would invent half of it: if nobody reported breadth, the summary SAYS so instead of showing the
    number of cards as if it were the explored count."""
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
    """Install + session ids for the SUMMARY tab's audit strip (V2-538). Served IN the payload because the
    widget contract bans network in widget.js — the strip's own fetch was the violation that kept
    `make test-widgets` permanently red (V2-601 T-10). Fail-open to {}: no identity, no strip, as before.
    (The engine import below is why `results` sits in the validator's curated `_STDLIB_EXEMPT`, with the
    observer emit of `_audit` — this widget IS an engine surface, the errand sheet.)"""
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
