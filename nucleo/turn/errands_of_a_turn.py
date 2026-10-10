"""Every errand one turn asks for either STARTS or is SAID not to have started (three-tasks-at-once, 2026-10-10).

A turn can carry several errands — «hazme un informe, búscame un monitor y móntame un juego» — and three doors
used to drop one of them without a word, each for a reason that is right on its own case:

  · the LISTING lane is skipped when the turn also escalated, because two workers on the SAME hunt race each other
    — and a DIFFERENT hunt (the monitor beside a report and a game) was dropped with it;
  · a turn whose yes/no resolved a parked errand cleared all of its escalations, because «it answers what is
    parked» — and an unrelated errand ordered in the same breath vanished;
  · the per-turn cap (the worker pool) dropped the fourth errand silently.

The rules are here, once, and both channels call them: a hunt that is not one of the escalations rides as one
more; what the answer resolved is taken out and the rest stays; what the pool cannot take is named back to him.
«Same errand» is the dedup's own yardstick (`matching.containment`), never a second one.
"""
from __future__ import annotations

#: Errands one turn may open — the worker pool's default width (`dispatch._max_parallel`), as before.
MAX_ERRANDS = 3


def same_errand(a: str, b: str) -> bool:
    """The dedup's measure: is the smaller set of content words inside the bigger one?"""
    from nucleo import matching
    wa, wb = matching.content_words(a), matching.content_words(b)
    return bool(wa and wb) and matching.containment(wa, wb) >= matching.SAME_ERRAND


def listing_errand(listing: dict) -> str:
    """A `search_listings` call written as an errand for a worker: the hunt and the bounds he gave."""
    q = str((listing or {}).get("query") or "").strip()
    bounds = [f"max price {listing['price_max']}" if listing.get("price_max") not in (None, "") else "",
              f"min price {listing['price_min']}" if listing.get("price_min") not in (None, "") else "",
              f"condition: {listing['condition']}" if str(listing.get("condition") or "").strip() else ""]
    bounds = [b for b in bounds if b]
    return (f"Find real marketplace listings for: {q}" + (f" ({'; '.join(bounds)})" if bounds else "")
            + ". Put the real candidates, with price and link, on the results sheet.") if q else ""


def listing_rides(listing: dict | None, requests: list[str]) -> str:
    """The listing hunt as ONE MORE errand when the turn escalated others and it is none of them; "" otherwise.

    Alone, the hunt is the fast lane's (`listing_turn.voice_turn`). Beside an escalation of the SAME hunt it stays
    dropped — two workers racing one hunt is the defect the skip was written for."""
    reqs = [r for r in (requests or []) if str(r or "").strip()]
    if not listing or not reqs:
        return ""
    q = str(listing.get("query") or "").strip()
    if not q or any(same_errand(q, r) for r in reqs):
        return ""
    return listing_errand(listing)


def beside_an_answer(resolved: str, requests: list[str]) -> list[str]:
    """The turn's escalations that are NOT the errand its yes/no just resolved — those are still orders."""
    return [r for r in (requests or []) if r and not (resolved and same_errand(r, resolved))]


def keep_beside_an_answer(escalate_req: dict, resolved: str | None) -> None:
    """The voice turn's `escalate_req`, cut down to what the answer did not resolve (the confirmed errand is
    relaunched by `resolve_confirm`; re-escalating it would open it twice). `resolved=None` — an answer that names
    no errand, a click held in the browser — keeps today's rule: the turn opens nothing new."""
    rest = ([] if resolved is None
            else beside_an_answer(resolved, [escalate_req.get("v"), *(escalate_req.get("more") or [])]))
    escalate_req["v"], escalate_req["more"] = (rest[0] if rest else None), rest[1:]


def within_the_pool(requests: list[str]) -> tuple[list[str], list[str]]:
    """(what starts, what the pool cannot take this turn)."""
    reqs = list(requests or [])
    return reqs[:MAX_ERRANDS], reqs[MAX_ERRANDS:]


def not_started_line(dropped: list[str]) -> str:
    """The sentence that names, in his language, the errands this turn did NOT start. "" when none."""
    items = [str(d).strip().rstrip(".")[:90] for d in (dropped or []) if str(d or "").strip()]
    if not items:
        return ""
    from i18n import langs as _lg
    return _lg.current_language().errands_not_started.format(what="; ".join(f"«{i}»" for i in items))
