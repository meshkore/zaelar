"""The search door (refactor2710-06 T-05): every search a turn makes crosses here, over `search.find()`.

Two acts, `(request, args) → Outcome`, where `request` is the turn (`text`, `brief`) and `args` the tool's call:

  · `fact` — a fact for this turn: the route the service would take (a shadow row, V2-782 F4), `find(route=
    "inline_fact")`, and what came back on the timeline with its evidence. `compose_system` hands the composing
    pass WHY an empty search was empty, and `denial_repair` replaces a reply that denies having the internet: the
    evidence reaches the reader, not only the timeline (V2-676).
  · `listings` — the listing fast pass (V2-556): enough rows land in ONE sheet now; not enough → the same sheet is
    inherited by a Brain Worker (the `worker.spawn` door) and the turn says the deeper search is under way. The
    model never chooses fast-vs-deep.

The service owes the turn nothing (CRIT-S6): the turn imports `search`, never the reverse.
"""
from __future__ import annotations

import time

from loguru import logger

from nucleo.acts.outcome import Outcome
from nucleo.circuit import verdict as V
from search.route import SEARCH_KEY, Route, search_route
from search.web import format_results

#: Spoken-answer budget of both composing passes.
MAX_TOKENS = 240


def _note(what: str) -> None:
    logger.debug(f"acts.search: {what}")


# ── the fact ─────────────────────────────────────────────────────────────────────────────────────────────────

def verdicts_from_brief(brief) -> dict:
    """`{search_module, escalate_or_inline, errand_surface}` as `(choice, confidence)`, read at any confidence: the
    service applies its own floors and says which it used."""
    out: dict = {}
    try:
        from nucleo import surfaces as _sf
        from nucleo.turn import brief as _tb
        for key in (SEARCH_KEY, _tb.ESCALATE_KEY, _sf.SURFACE_KEY):
            choice, info = _tb.read(brief, key, "", min_confidence=0.0)
            if choice and isinstance(info, dict):
                out[key] = (str(choice), float(info.get("confidence") or 0.0))
    except Exception as e:  # noqa: BLE001 — no brief reads as no verdicts; the service routes on the proposal
        _note(f"the brief was not read ({e!r}); routing on the proposal alone")
    return out


def route_for(query: str, *, proposal: str, brief, named_site: bool = False) -> Route:
    return search_route(query, proposal=proposal, verdicts=verdicts_from_brief(brief), named_site=named_site)


def shadow(query: str, *, proposal: str, brief, emit, channel: str) -> Route | None:
    """Emit the route the service would take for this search. Never raises, never changes the turn."""
    try:
        rt = route_for(query, proposal=proposal, brief=brief)
        emit("brain", "🧭 ruta de búsqueda (sombra)", text=str(query)[:160], role="system",
             extra={"cat": "flash", "src": channel, "proposal": proposal, **rt.to_dict()})
        return rt
    except Exception as e:  # noqa: BLE001
        _note(f"no shadow route ({e!r})")
        return None


def _find_fact(query: str) -> dict:
    """`find(route="inline_fact")` as the chain's dict the composing pass reads, the failure carried. Never raises."""
    try:
        from search import find as _find
        sres = _find(query, route="inline_fact", proposal="web_search")
        out = dict(sres.raw or {"query": query, "answer": "", "results": [], "source": "none",
                                **({"failure": sres.failure} if sres.failure else {})})
        from nucleo.flash import amount_gate as _ag
        _ag.note_search(out)            # what it returned is what may back a figure in the reply
        return out
    except Exception as e:  # noqa: BLE001 — the turn goes on without the web, and says why on the timeline
        logger.warning(f"acts.search: the fact door failed ({e!r})")
        return {"query": query, "answer": "", "results": [], "source": "none",
                "failure": {"kind": "error", "detail": f"{type(e).__name__}: {str(e)[:160]}"}}


def fact(request: dict, args: dict, *, emit, channel: str) -> Outcome:
    """Search the web for this turn's fact. BLOCKING (callers on the loop run it in a thread); never raises.
    `data` carries `res` (the chain's dict) and `ctx` (the results as the composing pass reads them). The row says
    WHAT came back — titles, URLs, snippets and the synthesized answer — so an audit can tell what the reply read."""
    query = str((args or {}).get("query") or "").strip()
    emit("brain", "🔎 búsqueda web", text=query, role="system")
    t0 = time.time()
    shadow(query, proposal="web_search", brief=(request or {}).get("brief"), emit=emit, channel=channel)
    res = _find_fact(query)
    ev = {"source": res.get("source"), "ai": bool(res.get("ai")), "ms": round((time.time() - t0) * 1000),
          "n": len(res.get("results", [])), **({"failure": res["failure"]} if res.get("failure") else {})}
    try:
        from observability import evidence as _evd
        ev["evidence"] = _evd.web_results(res.get("results"))
        if _evd.body(res.get("answer")):
            ev["evidence"]["answer"] = _evd.body(res.get("answer"))
    except Exception as e:  # noqa: BLE001 — the row leaves without its evidence rather than not at all
        _note(f"no evidence on the row ({e!r})")
    emit("search", "🔎 resultados web", text=query, role="system", extra=ev)
    found = bool(res.get("results") or res.get("answer"))
    return Outcome(True, (V.MET if found else V.UNMET).name, data={"res": res, "ctx": format_results(res)})


def _why_empty(res: dict) -> str:
    """What the composing pass is told when the search came back with nothing: the forbidden sentence is NAMED,
    because «be honest» is advice and «never say this» is a rule (session af4429e0: five blocked searches answered
    with «I don't have live internet access»)."""
    kind = str(((res or {}).get("failure") or {}).get("kind") or "").lower()
    if kind == "captcha":
        why = ("el buscador te ha respondido con una VERIFICACIÓN ANTI-ROBOT (captcha) y por eso no hay "
               "resultados")
    elif kind == "quota":
        why = "el buscador ha agotado su cuota por ahora y por eso no hay resultados"
    elif kind:
        why = f"la búsqueda ha fallado ({kind}) y por eso no hay resultados"
    else:
        why = "la búsqueda no ha devuelto nada útil esta vez"
    return (f"\n\nOJO — LA BÚSQUEDA SÍ SE HA HECHO: {why}. "
            "Dilo tal cual: que has mirado y que esta vez no has podido traer el dato, y ofrécete a mirarlo "
            "a fondo con el navegador. "
            "PROHIBIDO decir que no tienes acceso a internet, que no puedes consultar información en tiempo "
            "real, que solo tienes datos de entrenamiento o que tienes una fecha de corte: es FALSO —tienes "
            "buscador y navegador— y quien te escucha es el dueño de este sistema.")


def compose_system(operator_text: str, query: str, res: dict, ctx: str, *, today: str = "",
                   on_screen: list | None = None) -> str:
    """The system prompt for the pass that turns web results into one spoken answer. It answers HIS question, not
    the model's query (V2-135: «opening hours AND price» searched as «opening hours» lost its second half)."""
    from nucleo.turn.prompt import builder as _prompt
    head = _prompt._lang_lock() + (f"\nHOY es {today}." if today else "")
    body = (
        "\nEl operador preguntó algo que requería BUSCAR en la web. Con estos RESULTADOS, responde a su "
        "pregunta en 1-2 frases HABLADAS: natural, sin markdown, sin emojis, sin leer URLs ni números de "
        "fuente. Si la pregunta es SENSIBLE A LA FECHA (el tiempo, una cotización, un resultado, algo «de "
        "hoy/ahora»): da el dato VIGENTE de hoy en adelante, nunca uno caducado, y si procede menciona el "
        "día. "
        "Contesta TODO lo que preguntó (si pidió dos datos, los dos); si los resultados solo cubren una "
        "parte, di CUÁL falta y ofrécete a mirarla — no la dejes caer en silencio. "
        "Si los resultados NO contienen la respuesta clara, dilo con naturalidad; NO inventes datos que no "
        "estén en ellos."
    )
    # An answer-only provider (Gemini grounding) can bring the fact with no ranked pages; that is not «nothing».
    tail = "" if ((res or {}).get("results") or (res or {}).get("answer")) else _why_empty(res)
    if on_screen:
        # What THIS turn already put in front of him: the card answers the visual half, the results the spoken one.
        tail += (f"\nEN PANTALLA, abierto en este mismo turno: {', '.join(on_screen)}. Eso YA se le está "
                 "enseñando: no digas que no puedes mostrarlo; completa con el dato de los resultados.")
    return (head + body + tail
            + f"\n\nPREGUNTA DEL OPERADOR: {operator_text}"
            + f"\nBÚSQUEDA REALIZADA: {query}\n\nRESULTADOS:\n{ctx or '(sin resultados)'}")


def denial_repair(reply: str, res: dict) -> str:
    """The composed reply, or the TRUE sentence in his language when it denies the capability — whatever the
    results were: an agent telling its owner it has no internet is a false claim about the product."""
    from nucleo.flash import answer_guards as _ag
    if not _ag.a_reply_denies_the_world(reply):
        return reply
    try:
        from i18n import langs as _lg
        spec = _lg.current_language()
        return spec.search_blocked if ((res or {}).get("failure") or {}).get("kind") else spec.unverified_fact
    except Exception as e:  # noqa: BLE001
        _note(f"no language table ({e!r})")
        return "He mirado, pero esta vez no he podido traerte el dato. ¿Lo intento a fondo con el navegador?"


# ── the listings: the fast pass and its sheet live beside this door ─────────────────────────────────────────
from nucleo.acts.search_listing import (TOOL_DEF, compose_context, compose_face, fast_pass,  # noqa: E402,F401
                                        listings, request_from, runs_alone)
