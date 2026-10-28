"""The listing fast pass and the ONE sheet it writes (V2-556 / V2-570; refactor2710-06 T-05).

`fast_pass` is blocking (network) and never raises; the turn runs it in a thread through `search_listing.listings`.
"""
from __future__ import annotations

import time

from loguru import logger

#: The ladder's own deadline. Kept equal to `ListingQuery.min_needed`'s default horizon: ONE definition of «enough».
_BUDGET_S = 10.0


def _note(what: str) -> None:
    logger.debug(f"acts.search_sheet: {what}")


def _country() -> str:
    """The engine's country, from the ENGINE's language — never a per-turn guess."""
    try:
        from i18n import langs
        code = (langs.current_code() or "es").lower()
    except Exception as e:  # noqa: BLE001 — a search must never die because the language is unreadable
        _note(f"no language ({e!r})")
        code = "es"
    return "ES" if code == "es" else "US"


def _fmt_price(item: dict) -> str:
    """A price the sheet can PRINT, in the page's own currency: a silent conversion is what the boat case forbids."""
    price, cur = item.get("price"), (item.get("currency") or "").strip()
    if price is None:
        return ""
    n = f"{price:,.0f}".replace(",", ".") if float(price) == int(price) else f"{price:,.2f}"
    return f"{n} {cur}".strip() if cur else n


def _to_row(item: dict) -> dict:
    """One listing item → one results-sheet row (the sheet's closed schema, `data._ITEM_FIELDS`)."""
    row: dict = {"title": str(item.get("title") or "").strip()}
    bits = [b for b in (item.get("location"), item.get("source")) if b]
    if bits:
        row["subtitle"] = " · ".join(str(b) for b in bits)
    if _fmt_price(item):
        row["price"] = _fmt_price(item)
    for k in ("url", "image"):
        if str(item.get(k) or "").strip():
            row[k] = str(item[k]).strip()
    facts = [{"label": str(k), "value": str(v)} for k, v in list((item.get("attributes") or {}).items())[:6]
             if str(v).strip()]
    if facts:
        row["facts"] = facts
    return row


def _source_rows(sources: list[dict]) -> list[dict]:
    """The ladder's audit trail → the sheet's SOURCES tab; the blocked doors especially."""
    out = []
    for s in sources or []:
        row = {"name": f"{s.get('tier', '?')}: {s.get('target', '')}".strip(": "), "status": str(s.get("status") or "")}
        if s.get("n") is not None:
            row["found"] = int(s.get("kept", s.get("n")) or 0)
        if s.get("note"):
            row["note"] = str(s["note"])[:160]
        out.append(row)
    return out[:20]


def compose_context(result: dict) -> str:
    """What the composing pass READS: real rows, compactly, never URLs."""
    lines = []
    for it in (result.get("items") or [])[:8]:
        bits = [str(it.get("title") or "")[:80], _fmt_price(it), str(it.get("location") or "").strip(),
                str(it.get("source") or "").strip()]
        lines.append(" — ".join(b for b in bits if b))
    return "\n".join(f"· {ln}" for ln in lines)


def _write_sheet(sid: str, title: str, items: list, res: dict, *, inherited: bool, delivered: bool,
                 asked: str) -> None:
    """The rows (and the doors tried) into the sheet. A refined re-run that found nothing keeps the earlier delivery:
    `present` with an empty list REPLACES the items, and wiping an answered box is what V2-259 closed."""
    try:
        from widgets.results import data as sheet_mod
        if inherited and not items:
            sheet_mod.rename_task(title, sheet=sid)
        else:
            (sheet_mod.rename_task if inherited else sheet_mod.begin_task)(title, sheet=sid)   # inherited: its criteria stay
            payload: dict = {"sheet": sid, "items": [_to_row(i) for i in items],
                             "sources": _source_rows(res.get("sources") or []),
                             "criteria": {"objective": asked}, "asked": asked}
            if not items:
                payload["note"] = sheet_mod.note_text(*(("note_none", "No results.") if delivered
                                                        else ("note_searching_deep", "Searching in depth…")))
            sheet_mod.apply_action("present", payload)
        sheet_mod.prune_sheets()
        from voice.observer import emit as _emit
        _emit("widget", "show", extra={"id": sheet_mod.instance_id(sid), "src": "listing_turn"})
    except Exception as e:  # noqa: BLE001 — rows that cannot reach the sheet must not kill the turn
        logger.warning(f"acts.search_sheet: the sheet refused the delivery ({e!r})")


def _hand_on(delivered: bool, asked: str, sid: str, n: int) -> int:
    """A delivery is a FACT later escalations of the same hunt read (V2-570); no delivery → the same goal, the same
    sheet, a Brain Worker (the `worker.spawn` door). Returns the worker's task id, 0 when none."""
    try:
        if delivered:
            from nucleo.workers import ended as _ended
            _ended.note_listing_delivery(asked, sid, n=n)
            return 0
        from nucleo.flash.escalate import escalate_to_slowbrain
        return escalate_to_slowbrain(asked, context={"sheet": sid, "surface": "lista"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"acts.search_sheet: no hand-on ({e!r})")
        return 0


def fast_pass(query: str, *, price_max=None, price_min=None, condition: str = "",
              operator_text: str = "", budget_s: float = _BUDGET_S, sheet: str = "", new_sheet: str = "") -> dict:
    """The fast pass, start to verdict: `{delivered, n, sheet, escalated, reason, ms, ctx}`. Delivered → the sheet
    holds ≥ min_needed real rows; not → it holds what was found, and `escalated` is the worker's id. `sheet` is an
    INHERITED box (V2-570): a refined re-run lands in the sheet he is already looking at. The escalation's request
    is HIS words, never the model's reformulation (V2-135)."""
    t0 = time.time()
    query, operator_text = str(query or "").strip(), str(operator_text or "").strip()
    inherited = bool(str(sheet or "").strip())
    out = {"delivered": False, "n": 0, "sheet": "", "escalated": 0, "reason": "", "ms": 0, "ctx": ""}
    if not query:
        out["reason"] = "empty query"
        return out
    try:
        from search import listing as LS
        res = LS.search(LS.ListingQuery(text=query, countries=(_country(),), price_max=price_max,
                                        price_min=price_min, condition=str(condition or "").strip(),
                                        deadline_s=float(budget_s)))
    except Exception as e:  # noqa: BLE001 — the ladder promises not to raise; if it does, the turn survives
        logger.warning(f"acts.search_sheet: the ladder failed ({e!r})")
        res = {"items": [], "sources": [], "needs_browser": True, "reason": f"search failed: {e}"}
    items = res.get("items") or []
    delivered = not res.get("needs_browser", True)
    sid = str(sheet).strip() if inherited else (new_sheet or fresh_sheet())
    out.update(n=len(items), reason=str(res.get("reason") or ""), ctx=compose_context(res), sheet=sid)
    asked = operator_text or query
    _write_sheet(sid, " ".join(asked.split())[:80], items, res, inherited=inherited, delivered=delivered, asked=asked)
    out["delivered"] = delivered
    out["escalated"] = _hand_on(delivered, asked, sid, len(items))
    out["ms"] = round((time.time() - t0) * 1000)
    _observe(query, out, items, res)
    return out


def _observe(query: str, out: dict, items: list, res: dict) -> None:
    """The `search` family, like a web search: what came back and what was tried, so an audit tells «found nothing»
    from «never looked»."""
    extra = {"tier": "listing", "n": len(items), "delivered": out["delivered"], "escalated": out["escalated"],
             "sheet": out["sheet"], "ms": out["ms"], **({"reason": out["reason"]} if out["reason"] else {}),
             "evidence": {"results": [{"title": str(i.get("title") or "")[:120], "url": str(i.get("url") or "")[:200],
                                       "price": _fmt_price(i)} for i in items[:8]],
                          "sources": [{"name": f"{s.get('tier')}:{s.get('target')}", "status": s.get("status")}
                                      for s in (res.get("sources") or [])[:12]]}}
    try:
        from voice.observer import emit as _emit
        _emit("search", "🛒 búsqueda de anuncios", text=query, role="system", extra=extra)
    except Exception as e:  # noqa: BLE001
        _note(f"the row did not leave ({e!r})")


from nucleo.acts.search_listing import fresh_sheet  # noqa: E402 — minted by the turn, used here when it did not
