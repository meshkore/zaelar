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


#: The tool as FlashBrain sees it. It lives here, not in the router's catalog, because the argument names and
#: what each one may carry are this module's contract — the router places it, the module defines it. Wording is
#: load-bearing and gated: the catalog has a total budget and a per-tool ceiling (node 2.13's compactness test).
TOOL_DEF = {
    "type": "function",
    "function": {
        "name": "search_listings",
        "description": (
            "Busca ANUNCIOS/productos en venta o alquiler (coche, piso, portátil, entradas…): resultados "
            "reales con precio y enlace en la hoja de resultados. Si el mercado no da bastante, este sistema "
            "lanza ÉL SOLO la búsqueda a fondo: di que sigues buscando y JAMÁS llames además a "
            "escalate_to_slowbrain por la misma caza. No es un dato puntual (web_search) ni HACER algo en "
            "una web (escalate_to_slowbrain). CONSERVA los filtros que el operador no retiró."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Qué se busca, autocontenido; SIN el precio (va aparte)."},
                "price_max": {"type": "number", "description": "Precio máximo (solo número), si lo dio."},
                "price_min": {"type": "number", "description": "Precio mínimo (solo número), si lo dio."},
                "condition": {"type": "string", "description": "nuevo/usado/reacondicionado, si lo dijo."},
            },
            "required": ["query"],
        },
    },
}


def request_from(args: dict, fallback_text: str) -> dict:
    """The `search_listings` call as this module's request. ONE per turn: the first with a real query wins.

    Same shape as `image_turn.request_from`, and here for the same two reasons: the callers are god files with a
    ceiling, and the argument names are this module's contract — a channel should not have to know that an empty
    `query` falls back to the operator's own words (V2-135: a reformulation loses what the words carried).

    It does NOT compete with `escalate_to_slowbrain`: if the model called both for the SAME hunt, the router's
    priority already collapses the turn into the escalation, and the module is the one that decides fast-vs-deep.
    """
    return {"query": str(args.get("query") or "").strip() or str(fallback_text or "").strip(),
            "price_max": args.get("price_max"), "price_min": args.get("price_min"),
            "condition": str(args.get("condition") or "").strip()}


async def voice_turn(req: dict, operator_text: str, *, spec=None, on_delta=None) -> "tuple[dict, str]":
    """The WHOLE body of both channels' `search_listings` branch: fast pass + composed spoken reply.

    It lives here and not there for the reason `image_turn.voice_turn` already states: the voice provider and
    `probe` are god files with a ceiling, and the ratchet asks to EXTRACT before adding to them. It is also the
    honest boundary — this module already owns the fast-vs-deep verdict and the face that tells it, so it owns
    running them in order too, and the two channels are left with a call instead of a copy of the sequence.

    `on_delta` streams each fragment as it arrives (voice speaks while composing); `probe` accumulates and
    passes nothing. `run` is blocking, so it goes to a thread (V2-011) — HERE, once, rather than in each caller.
    `CancelledError` is re-raised on purpose: a cancelled turn must not look like a failed search.
    """
    import asyncio
    try:
        res = await asyncio.to_thread(
            run, str(req.get("query") or ""), price_max=req.get("price_max"),
            price_min=req.get("price_min"), condition=str(req.get("condition") or "").strip(),
            operator_text=operator_text)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — a search that explodes must not take the turn with it
        logger.warning(f"listing_turn: la pasada rápida falló, el turno sigue ({e!r})")
        res = {"delivered": False, "n": 0, "escalated": 0, "ctx": "", "reason": str(e), "sheet": ""}
    said = ""
    try:
        from .fast_client import FastClient
        parts: list[str] = []
        async for delta in FastClient().stream(
                [{"role": "system", "content": compose_face(res, operator_text)},
                 {"role": "user", "content": operator_text}], spec=spec, max_tokens=240):
            parts.append(delta)
            if on_delta is not None:
                on_delta(delta)
        said = "".join(parts)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — la entrega ya está en la hoja; sin composición el turno sigue vivo
        logger.warning(f"listing_turn: la cara no compuso ({e!r})")
    return res, said


def compose_face(res: dict, operator_text: str) -> str:
    """The system prompt that turns a fast-pass verdict into a SPOKEN reply. ONE definition, both channels.

    This lived DUPLICATED in the voice provider and in `probe.py` — the two-channels rule wired the CALL in
    both and left the WORDING in both too, which is the same failure one level up: two copies of a prompt
    drift, and a prompt that drifts fails silently (the model just says something else). It is extracted here
    because the face is part of the module's contract: the box decides fast-vs-deep, so the box also owns how
    that verdict is told.

    The escalated branch is where V2-556's run v3 lost a delivery. The old text stated the partial count as a
    FACT next to an imperative that only ordered «say the deep search is underway» — and the model obeyed the
    imperative and dropped the fact: four real cars on the sheet, answered with «en cuanto tenga resultados
    específicos te los digo». So the rows go INSIDE the order, and they go by NAME: `res["ctx"]` already holds
    the spoken rows on BOTH branches, which is exactly the datum the old face threw away.
    """
    from . import prompt as _prompt
    head = _prompt._lang_lock()
    ctx = str(res.get("ctx") or "").strip()
    ask = str(operator_text or "").strip()
    if res.get("delivered"):
        return (head
                + "\nEl operador pidió BUSCAR anuncios/productos y la búsqueda YA se hizo: los anuncios de "
                "abajo son REALES y ya están en su hoja de resultados, en pantalla. Respóndele en 1-2 frases "
                "HABLADAS: cuántos hay, el rango de precios y lo más prometedor, y que los tiene en la hoja. "
                "Natural, sin markdown, sin emojis, sin leer URLs. No inventes NADA que no esté en la lista; "
                "si un dato que pidió no está (kilómetros, estado), dilo.\n\n"
                f"PETICIÓN DEL OPERADOR: {ask}\n\nANUNCIOS ENCONTRADOS:\n{ctx}")
    tiene = bool(res.get("n")) and bool(ctx)
    return (head
            + "\nEl operador pidió BUSCAR anuncios/productos. La pasada rápida no encontró SUFICIENTE y una "
            "BÚSQUEDA A FONDO ya está EN MARCHA (no hay que lanzarla ni pedir permiso: ya corre, y sus avances "
            "van saliendo en su hoja de resultados). Díselo en 1-2 frases HABLADAS: que vas a investigar a "
            "fondo y que verá los avances en la hoja. Natural, sin markdown, sin emojis, sin URLs. NO prometas "
            "plazos."
            + (" Y EN ESA MISMA RESPUESTA, PRIMERO: NÓMBRALE los anuncios de abajo con su precio. Ya están en "
               "su pantalla — tenerlos y no nombrarlos es negarle una entrega que ya tiene."
               if tiene else "")
            + f"\n\nPETICIÓN DEL OPERADOR: {ask}"
            + (f"\n\nANUNCIOS PROVISIONALES YA EN SU HOJA ({res.get('n')}):\n{ctx}" if tiene else ""))


def run(query: str, *, price_max=None, price_min=None, condition: str = "",
        operator_text: str = "", budget_s: float = _BUDGET_S, sheet: str = "") -> dict:
    """The fast pass, start to verdict. Never raises; BLOCKING (call via `asyncio.to_thread` from the loop).

    Returns `{delivered, n, sheet, escalated, reason, ms, ctx}`:
      · `delivered` True  → the sheet holds ≥ min_needed real rows; the turn answers with them (`ctx`).
      · `delivered` False → the sheet holds whatever was found plus the doors tried, and `escalated` carries
        the Brain Worker's task id (0 if even escalating failed). The turn says a deeper search is underway.

    `sheet` (V2-570): an INHERITED box — the linear gate re-runs a just-delivered hunt with the refined query
    into the SAME sheet the operator is already looking at, instead of minting a second one. With rows found
    the refined delivery REPLACES the earlier, less-specified one (same hunt, better query); with nothing
    found the previous delivery is NOT wiped — a blank box in exchange for a refinement would be losing an
    answer the operator already had.
    """
    t0 = time.time()
    query = str(query or "").strip()
    operator_text = str(operator_text or "").strip()
    inherited = bool(str(sheet or "").strip())
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
    if inherited:
        sid = str(sheet).strip()
    else:
        try:
            from nucleo.runtime_ids import next_seq
            from nucleo.sheets import sheet_id_for
            sid = sheet_id_for(f"ls{next_seq('listing.fast')}")
        except Exception:  # noqa: BLE001
            sid = ""
    out["sheet"] = sid

    try:
        from widgets.results import data as sheet_mod
        title = " ".join((operator_text or query).split())[:80]
        if inherited and not items:
            # A refined re-run that found nothing keeps the previous delivery on screen: `present` with an
            # empty list REPLACES the items, and wiping an answered box in exchange for nothing is the
            # «estrenar = borrar» failure V2-259 closed. The deep pass this branch escalates to will write.
            sheet_mod.rename_task(title, sheet=sid)
        else:
            sheet_mod.begin_task(title, fresh=True, sheet=sid)
            payload: dict = {"sheet": sid, "items": [_to_row(i) for i in items],
                             "sources": _source_rows(res.get("sources") or []),
                             "criteria": {"objective": operator_text or query}}
            if not items:
                payload["note"] = "Buscando a fondo…" if not delivered else "Sin resultados."
            sheet_mod.apply_action("present", payload)
        sheet_mod.prune_sheets()
        try:
            from voice.observer import emit as _emit
            _emit("widget", "show", extra={"id": sheet_mod.instance_id(sid), "src": "listing_turn"})
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001 — rows that cannot reach the sheet must not kill the turn
        logger.warning(f"listing_turn: la hoja no aceptó la entrega ({e!r})")

    if delivered:
        out["delivered"] = True
        # V2-570 — a delivery is a FACT the engine can see: it is what lets a later escalation of the same
        # hunt inherit this box and be redirected to a refined fast re-run instead of a parallel worker.
        # Recorded even when the launching turn was discarded (a superseded fragment's late delivery is
        # exactly the case where the NEXT turn needs to know this search already ran).
        try:
            from nucleo.workers import ended as _ended
            _ended.note_listing_delivery(operator_text or query, sid, n=len(items))
        except Exception:  # noqa: BLE001
            pass
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
