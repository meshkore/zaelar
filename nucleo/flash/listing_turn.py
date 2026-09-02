"""nucleo/flash/listing_turn.py — the LISTING fast pass: one turn, one sheet, and an honest handoff (V2-556 P1).

The circuit this module closes, in the operator's own framing: the search module is a box — an input goes in,
an output comes out — and the box DECIDES whether it can serve the turn or the errand needs a Brain Worker.
FlashBrain calls ONE tool (`search_listings`, router.py) and never chooses between fast and deep itself:

  1 · run `nucleo/listing_search.search` with a single-digit-second deadline (the module's ladder:
      SERP → HTTP+JSON-LD → Unlocker; free chain without a token);
  2 · ENOUGH listings → they land in the results sheet NOW, with their sources, and the turn answers with
      real rows on screen. Seconds, not minutes — the V2-457 asymmetry (355 s worker vs 3 s warm path)
      applied to listings;
  3 · NOT enough → the same sheet keeps what the fast pass DID find and which doors it tried, and the errand
      escalates to a Brain Worker that INHERITS the sheet (`ctx["sheet"]`, the V2-117 relay seam — dispatch
      opens it `fresh=False`, so the prefill survives). The operator is told a deeper search is underway and
      can watch it in the very box that already shows the first findings.

Why the sheet is minted HERE and not by the errand: the whole point of the handoff is that the operator keeps
looking at ONE box from first fast finding to final worker report. An errand mints its sheet from its own
task id (`sheet_id_for`), so the fast pass mints a different id and passes it down — exactly what a relay does
when a provider runs out of quota, and it reuses that inheritance seam rather than inventing a second one.

Both channels (voice provider and probe) call THIS body — the V2-539 lesson: two channels wired separately is
how one of them silently stops taking the decision the other one measures. Blocking by design (network);
the voice caller wraps it in `asyncio.to_thread`, same as `websearch`.
"""
from __future__ import annotations

import time

from loguru import logger

#: Below this, rows on screen read as an excuse, not an answer — the deep pass is launched instead.
#: Kept equal to `ListingQuery.min_needed`'s default on purpose: ONE definition of "enough".
_BUDGET_S = 10.0


def _country() -> str:
    """The engine's own country, the same way `browser_search._where()` derives it: the search follows the
    ENGINE's language, never a per-turn guess."""
    try:
        from voice.engine.core import langs
        code = (langs.current_code() or "es").lower()
    except Exception:  # noqa: BLE001 — a search must never die because the language is unreadable
        code = "es"
    return "ES" if code == "es" else "US"


def _fmt_price(item: dict) -> str:
    """A price the sheet can PRINT. The float is for filtering; what the operator reads keeps the page's own
    currency — silently converting currencies is exactly what the boat use case forbids."""
    price, cur = item.get("price"), (item.get("currency") or "").strip()
    if price is None:
        return ""
    n = f"{price:,.0f}".replace(",", ".") if float(price) == int(price) else f"{price:,.2f}"
    return f"{n} {cur}".strip() if cur else n


def _to_row(item: dict) -> dict:
    """One `listing_search` item → one results-sheet row (the sheet's closed schema, `data._ITEM_FIELDS`)."""
    row: dict = {"title": str(item.get("title") or "").strip()}
    bits = [b for b in (item.get("location"), item.get("source")) if b]
    if bits:
        row["subtitle"] = " · ".join(str(b) for b in bits)
    p = _fmt_price(item)
    if p:
        row["price"] = p
    for k in ("url", "image"):
        v = str(item.get(k) or "").strip()
        if v:
            row[k] = v
    attrs = item.get("attributes") or {}
    facts = [{"label": str(k), "value": str(v)} for k, v in list(attrs.items())[:6] if str(v).strip()]
    if facts:
        row["facts"] = facts
    return row


def _source_rows(sources: list[dict]) -> list[dict]:
    """The ladder's own audit trail → the sheet's SOURCES tab. Every door tried is a row — the blocked ones
    especially: «which pages would not let us in» is the first thing the deep pass (and the operator) asks."""
    out = []
    for s in sources or []:
        name = f"{s.get('tier', '?')}: {s.get('target', '')}".strip(": ")
        row = {"name": name, "status": str(s.get("status") or "")}
        if s.get("n") is not None:
            row["found"] = int(s.get("kept", s.get("n")) or 0)
        if s.get("note"):
            row["note"] = str(s["note"])[:160]
        out.append(row)
    return out[:20]


def compose_context(result: dict) -> str:
    """What the second model pass READS to speak the answer: real rows, compactly, never URLs."""
    lines = []
    for it in (result.get("items") or [])[:8]:
        bits = [str(it.get("title") or "")[:80]]
        p = _fmt_price(it)
        if p:
            bits.append(p)
        loc = str(it.get("location") or "").strip()
        if loc:
            bits.append(loc)
        src = str(it.get("source") or "").strip()
        if src:
            bits.append(src)
        lines.append(" — ".join(b for b in bits if b))
    return "\n".join(f"· {ln}" for ln in lines)


def run(query: str, *, price_max=None, price_min=None, condition: str = "",
        operator_text: str = "", budget_s: float = _BUDGET_S) -> dict:
    """The fast pass, start to verdict. Never raises; BLOCKING (call via `asyncio.to_thread` from the loop).

    Returns `{delivered, n, sheet, escalated, reason, ms, ctx}`:
      · `delivered` True  → the sheet holds ≥ min_needed real rows; the turn answers with them (`ctx`).
      · `delivered` False → the sheet holds whatever was found plus the doors tried, and `escalated` carries
        the Brain Worker's task id (0 if even escalating failed). The turn says a deeper search is underway.
    """
    t0 = time.time()
    query = str(query or "").strip()
    operator_text = str(operator_text or "").strip()
    out = {"delivered": False, "n": 0, "sheet": "", "escalated": 0, "reason": "", "ms": 0, "ctx": ""}
    if not query:
        out["reason"] = "empty query"
        return out

    try:
        from nucleo import listing_search as LS
        q = LS.ListingQuery(text=query, countries=(_country(),),
                            price_max=price_max, price_min=price_min,
                            condition=str(condition or "").strip(), deadline_s=float(budget_s))
        res = LS.search(q)
    except Exception as e:  # noqa: BLE001 — the module promises not to raise; if it does, the turn survives
        logger.warning(f"listing_turn: search irrecuperable ({e!r})")
        res = {"items": [], "sources": [], "needs_browser": True, "reason": f"search failed: {e}"}

    items = res.get("items") or []
    delivered = not res.get("needs_browser", True)
    out.update(n=len(items), reason=str(res.get("reason") or ""), ctx=compose_context(res))

    # ONE sheet from first finding to final report. Its id must NOT derive from the errand (none exists yet):
    # the escalation inherits it precisely because it is not its own (`_sheet_open`'s relay rule).
    try:
        from nucleo.runtime_ids import next_seq
        from nucleo.sheets import sheet_id_for
        sid = sheet_id_for(f"ls{next_seq('listing.fast')}")
    except Exception:  # noqa: BLE001
        sid = ""
    out["sheet"] = sid

    try:
        from widgets.results import data as sheet
        title = " ".join((operator_text or query).split())[:80]
        sheet.begin_task(title, fresh=True, sheet=sid)
        payload: dict = {"sheet": sid, "items": [_to_row(i) for i in items],
                         "sources": _source_rows(res.get("sources") or []),
                         "criteria": {"objective": operator_text or query}}
        if not items:
            payload["note"] = "Buscando a fondo…" if not delivered else "Sin resultados."
        sheet.apply_action("present", payload)
        sheet.prune_sheets()
        try:
            from voice.observer import emit as _emit
            _emit("widget", "show", extra={"id": sheet.instance_id(sid), "src": "listing_turn"})
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001 — rows that cannot reach the sheet must not kill the turn
        logger.warning(f"listing_turn: la hoja no aceptó la entrega ({e!r})")

    if delivered:
        out["delivered"] = True
    else:
        # The handoff: same goal, same sheet, deeper machinery. The REQUEST is the operator's own words —
        # the model's query is its reformulation, and V2-135 already taught us what reformulations lose.
        try:
            from nucleo.flash.escalate import escalate_to_slowbrain
            out["escalated"] = escalate_to_slowbrain(
                operator_text or query, context={"sheet": sid, "surface": "lista"})
        except Exception as e:  # noqa: BLE001
            logger.warning(f"listing_turn: no pude escalar ({e!r})")

    out["ms"] = round((time.time() - t0) * 1000)

    # Observability: the same `search` family as web_search — a listing search IS a search, and the family
    # names what it contains (V2-548). Evidence carries what came back and what was tried, so an audit can
    # tell «found nothing» from «never looked» without reading code.
    try:
        from voice.observer import emit as _emit
        extra = {"tier": "listing", "n": len(items), "delivered": out["delivered"],
                 "escalated": out["escalated"], "sheet": sid, "ms": out["ms"],
                 **({"reason": out["reason"]} if out["reason"] else {})}
        try:
            from observability import evidence as _evd
            extra["evidence"] = {
                "results": [{"title": str(i.get("title") or "")[:120], "url": str(i.get("url") or "")[:200],
                             "price": _fmt_price(i)} for i in items[:8]],
                "sources": [{"name": f"{s.get('tier')}:{s.get('target')}", "status": s.get("status")}
                            for s in (res.get("sources") or [])[:12]],
            }
        except Exception:  # noqa: BLE001
            pass
        _emit("search", "🛒 búsqueda de anuncios", text=query, role="system", extra=extra)
    except Exception:  # noqa: BLE001
        pass
    return out
