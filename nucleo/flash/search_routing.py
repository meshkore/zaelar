"""nucleo/flash/search_routing.py — the turn hands the search service what it knows, and the service routes (V2-782 F4).

The ONE place the brain talks to `search.route`. It reads the brief's verdicts — the routing question
(`search_module`), the escalate gate and the errand surface — into the plain dict `search_route` takes, so the
service never imports the brief, and the brief never has to know the service's vocabulary.

SHADOW FIRST (the V2-653 F0 pattern): `shadow()` is called on both channels wherever a `web_search` runs today and
EMITS the route the service would have taken, next to what the turn actually did. Nothing changes hands yet. The
gate to acting on it is written in the initiative (F4 → F5/F6): zero false routes over the recorded sessions.
A timeline row per search is what makes that measurable; a guess would not be.
"""
from __future__ import annotations

from loguru import logger

from search.route import SEARCH_KEY, Route, search_route
from search.web import format_results  # noqa: F401 — re-exported: the fact doors read the chain dict through one name


def verdicts_from_brief(brief) -> dict:
    """`{search_module, escalate_or_inline, errand_surface}` as `(choice, confidence)` pairs, from the turn brief.
    Reads with `min_confidence=0.0`: the service applies its own floors and says which it used."""
    out: dict = {}
    try:
        from nucleo import surfaces as _sf
        from nucleo.flash import turn_brief as _tb
        for key in (SEARCH_KEY, _tb.ESCALATE_KEY, _sf.SURFACE_KEY):
            choice, info = _tb.read(brief, key, "", min_confidence=0.0)
            if choice and isinstance(info, dict):
                out[key] = (str(choice), float(info.get("confidence") or 0.0))
    except Exception as e:  # noqa: BLE001 — no brief reads as no verdicts; the service falls back to the proposal
        logger.debug(f"search_routing: could not read the brief ({e!r}); routing on the proposal alone")
    return out


def route_for(query: str, *, proposal: str, brief, named_site: bool = False) -> Route:
    return search_route(query, proposal=proposal, verdicts=verdicts_from_brief(brief), named_site=named_site)


def fact_search(query: str, *, brief, emit, channel: str) -> dict:
    """The fact door of a channel: the shadow route row, then `find(route="inline_fact")`, returned as the chain's
    dict the composing pass reads (`raw`, with the failure carried when the chain collapsed). BLOCKING: callers
    on the loop run it in a thread. Never raises — a search that explodes is an empty result with its reason."""
    shadow(query, proposal="web_search", brief=brief, emit=emit, channel=channel)
    try:
        from search import find as _find
        sres = _find(query, route="inline_fact", proposal="web_search")
        return dict(sres.raw or {"query": query, "answer": "", "results": [], "source": "none",
                                 **({"failure": sres.failure} if sres.failure else {})})
    except Exception as e:  # noqa: BLE001 — the turn goes on without the web, and says why on the timeline
        logger.warning(f"search_routing: the fact door failed ({e!r})")
        return {"query": query, "answer": "", "results": [], "source": "none",
                "failure": {"kind": "error", "detail": f"{type(e).__name__}: {str(e)[:160]}"}}


def shadow(query: str, *, proposal: str, brief, emit, channel: str) -> Route | None:
    """Emit the route the service would take for this search. Never raises, never changes the turn."""
    try:
        rt = route_for(query, proposal=proposal, brief=brief)
        emit("brain", "🧭 ruta de búsqueda (sombra)", text=str(query)[:160], role="system",
             extra={"cat": "flash", "src": channel, "proposal": proposal, **rt.to_dict()})
        return rt
    except Exception:  # noqa: BLE001
        return None
