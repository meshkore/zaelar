"""The listing half of the search door (V2-556; refactor2710-06 T-05): one turn, one sheet, and an honest handoff.

`fast_pass` runs the listing ladder (`search.listing`: SERP → HTTP+JSON-LD → Unlocker) under a single-digit-second
deadline. ENOUGH rows land in the results sheet now and the turn answers with them; NOT enough → the same sheet keeps
what was found and which doors were tried, and a Brain Worker INHERITS it (`ctx["sheet"]`, the relay seam), so he
watches one box from the first finding to the final report. The sheet is minted HERE, never from the errand's id,
for exactly that reason. `listings` is the whole turn body both channels call: fast pass, then the spoken face.
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo.acts.outcome import Outcome
from nucleo.circuit import verdict as V

#: How long the turn waits for the fast pass before it speaks and lets it finish alone.
FAST_PASS_BUDGET_S = 12.0


def _note(what: str) -> None:
    logger.debug(f"acts.search_listing: {what}")


#: The tool as FlashBrain sees it; its argument names are this door's contract. Wording is load-bearing and gated
#: by the catalogue's budget (node 2.13).
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
    """The `search_listings` call as this door's args; an empty query falls back to his own words (V2-135)."""
    return {"query": str(args.get("query") or "").strip() or str(fallback_text or "").strip(),
            "price_max": args.get("price_max"), "price_min": args.get("price_min"),
            "condition": str(args.get("condition") or "").strip()}


def runs_alone(listing_req: dict, reveal_req: dict, escalate_req: dict) -> bool:
    """Does the turn's hunt run as its own fast lane? Beside escalations it never does (two workers on the SAME hunt
    race), but a DIFFERENT hunt rides with the turn's errands instead of being dropped (sandbox 20261010-145227-es)."""
    if listing_req.get("v") is None or reveal_req.get("v") is not None:
        return False
    if escalate_req.get("v") is None:
        return True
    from nucleo.turn import errands_of_a_turn as _eot
    rides = _eot.listing_rides(listing_req["v"], [escalate_req["v"], *(escalate_req.get("more") or [])])
    if rides:
        _full = len(escalate_req.setdefault("more", [])) >= _eot.MAX_ERRANDS - 1
        (escalate_req.setdefault("dropped", []) if _full else escalate_req["more"]).append(rides)
        escalate_req.setdefault("surface", {})[rides] = "lista"
    return False


def _taken_line() -> str:
    """The language table's «I'll let you know as soon as I have it»."""
    try:
        from i18n import langs as _langs
        lang = _langs.current_language()
        return str(getattr(lang, "filler_errand_taken", "") or getattr(lang, "work_started", "") or "")
    except Exception as e:  # noqa: BLE001
        _note(f"no taken line ({e!r})")
        return ""


def _late_fast_pass(task) -> None:
    """The fast pass that outlived its turn: its outcome is on the timeline, never lost in a thread."""
    import asyncio as _aio
    try:
        res = task.result() or {}
        from voice.observer import emit as _emit
        _emit("brain", "🛒 la pasada rápida acabó después del turno", role="system",
              text=f"delivered={bool(res.get('delivered'))} n={res.get('n', 0)} sheet={res.get('sheet', '')}",
              extra={"cat": "flash", **{k: res.get(k) for k in ("delivered", "n", "sheet")}})
    except _aio.CancelledError:
        _note("the loop went down before the late pass reported; its sheet write is unaffected")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"acts.search_listing: the late fast pass failed ({e!r})")


def _verdict(res: dict) -> str:
    return (V.MET if res.get("delivered") else V.STARTED if (res.get("escalated") or res.get("pending"))
            else V.UNMET).name


async def listings(request: dict, args: dict, *, spec=None, on_delta=None, already_said: str = "") -> Outcome:
    """The whole `search_listings` turn: fast pass, then the composed spoken face (`say`); `data` is the pass's own
    result. `on_delta` streams the face as it arrives. A search slower than `FAST_PASS_BUDGET_S` is not waited for:
    the turn says the errand is taken and `fast_pass` still writes the sheet (demo pass 52: ~40 s left the turn
    mute). `CancelledError` is re-raised: a cancelled turn must not look like a failed search."""
    import asyncio

    from nucleo.turn import flow_of as _flow, launches as _launches
    operator_text = str((request or {}).get("text") or "")
    taken = "" if (already_said or "").strip() else _taken_line()
    # V2-784 — the open flow this hunt belongs to: a live worker takes it as a refinement, a pass in flight or just
    # delivered is re-run into ITS sheet. Only a new flow mints a sheet.
    joined = await _flow.join(operator_text)
    if joined.get("injected"):
        if taken and on_delta is not None:
            on_delta(taken)
        return Outcome(True, V.STARTED.name, taken, {"delivered": False, "n": 0, "escalated": 0, "ctx": "",
                       "sheet": joined.get("sheet", ""), "pending": True, "joined": joined["flow"]})
    inherit = str(joined.get("sheet") or "")
    new_sheet = "" if inherit else fresh_sheet()
    lid = _launches.opened(operator_text or str(args.get("query") or ""), inherit or new_sheet)
    task = asyncio.ensure_future(asyncio.to_thread(
        fast_pass, str(args.get("query") or ""), price_max=args.get("price_max"), price_min=args.get("price_min"),
        condition=str(args.get("condition") or "").strip(), operator_text=operator_text, sheet=inherit,
        new_sheet=new_sheet))
    task.add_done_callback(lambda _t: _launches.closed(lid))   # by then its delivery or escalation carries it
    done, _pending = await asyncio.wait({task}, timeout=FAST_PASS_BUDGET_S)
    if not done:
        task.add_done_callback(_late_fast_pass)
        if taken and on_delta is not None:
            on_delta(taken)
        return Outcome(True, V.STARTED.name, taken, {"delivered": False, "n": 0, "escalated": 0, "ctx": "",
                                                     "sheet": "", "pending": True})
    try:
        res = task.result()
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — a search that explodes must not take the turn with it
        logger.warning(f"acts.search_listing: the fast pass failed, the turn goes on ({e!r})")
        res = {"delivered": False, "n": 0, "escalated": 0, "ctx": "", "reason": str(e), "sheet": ""}
    # The turn already SPOKE its promise and nothing landed yet: a second sentence would only repeat it. Rows are news.
    if (already_said or "").strip() and not res.get("delivered"):
        return Outcome(True, _verdict(res), "", res)
    face = compose_face(res, operator_text)
    if (already_said or "").strip():
        face += (f"\n\nYA LE HAS DICHO en este turno: «{already_said.strip()[:400]}». No lo repitas: di solo lo "
                 "que es nuevo (lo que ya está en la hoja).")
    said = ""
    try:
        from nucleo.flash.fast_client import FastClient
        parts: list[str] = []
        async for delta in FastClient().stream([{"role": "system", "content": face},
                                                {"role": "user", "content": operator_text}],
                                               spec=spec, max_tokens=240):
            parts.append(delta)
            if on_delta is not None:
                on_delta(delta)
        said = "".join(parts)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — the delivery is already on the sheet; the turn stays alive
        logger.warning(f"acts.search_listing: the face did not compose ({e!r})")
    return Outcome(True, _verdict(res), said, res)


def compose_face(res: dict, operator_text: str) -> str:
    """The system prompt that tells a fast-pass verdict, one definition for both channels. On the escalated branch
    the rows go INSIDE the order and by NAME: V2-556's run v3 had four cars on the sheet answered with «I'll tell you
    when I have results», because the count stood as a fact beside an imperative the model obeyed alone."""
    from nucleo.turn.prompt import builder as _prompt
    head = _prompt._lang_lock()
    ctx, ask = str(res.get("ctx") or "").strip(), str(operator_text or "").strip()
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


def fresh_sheet() -> str:
    """A new fast-pass sheet id, minted BEFORE the pass runs so the launch is a flow with its sheet from the start."""
    try:
        from nucleo.runtime_ids import next_seq
        from nucleo.sheets import sheet_id_for
        return sheet_id_for(f"ls{next_seq('listing.fast')}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"acts.search_listing: could not mint a sheet id ({e!r})")
        return ""


from nucleo.acts.search_sheet import compose_context, fast_pass  # noqa: E402,F401 — the blocking pass and its sheet
