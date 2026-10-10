"""search/route.py — WHICH search module serves this request (V2-782 T4.1).

Until 2026-10-10 the decision of which of six search paths ran was spread across the model's tool choice
(`web_search` / `search_listings` / `show_images` / `escalate_to_slowbrain`), `probe_decide`, the
`escalate_or_inline` verdict, the errand surface, `escalation_guard` and `card_commission`. No single place
answered «this request → this module», and the measured misroutes (§1 of the initiative) were all of the same
family: a quick fact escalated to a 5-minute worker; a hunt for listings answered from four web snippets; «dame
ideas para cenar» turned into 50 web searches and 265 s.

This module is that single place. It takes what the turn already KNOWS — the brief's verdicts, the model's own
tool proposal, whether a site was named — and returns one `Route`. The rules, in precedence order (CRIT-K2: the
verdict COMPLETES the model, the arbiter is precedence, not a third reader):

  1. The brief's own `search_module` verdict, when it is SURE (`SURE` and above). It is one more question in
     the turn brief Jev already answers (N questions cost one trip, `nucleo/jev.py`), worded below.
  2. The model's tool proposal, when it names a module (`search_listings` → listing, `show_images` → images).
     `web_search` is the model's generic «look it up» and is REFINED, not trusted blindly: the other verdicts
     say whether the turn was a fact or a commission.
  3. The brief's verdict when unsure, then `escalate_or_inline` + the errand surface, then the default.

No verb tables (V2-750, CRIT-K1): nothing here reads the operator's words to decide a module. The ONE reader
of his words is `criteria.breadth`, and it reads numerals, which travel with the route as the breadth the
brief should respect (T4.4).

Deterministic, pure, no network: the Jev question is asked by the TURN (the brief) or by a `judge` the caller
hands in; this module only reads answers. That is what makes the routing bank (`tests/search/bank/`) runnable
without a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from . import criteria as _criteria
from .result import BRAIN_WORKER, BROWSER, IMAGES, INLINE_FACT, LISTING, LOCAL_SERVICE, MODULES

#: The key under which the turn brief asks Jev the ONE routing question.
SEARCH_KEY = "search_module"

#: A verdict at or above this decides on its own; below it, the verdict only breaks ties.
SURE = 0.75
#: Below this a verdict is noise and is not read at all.
FLOOR = 0.5

INSTRUCTIONS = (
    "The operator asked the assistant to find something out or find something. Which kind of search serves it? "
    "A fact is looked up and answered on the spot. A listing hunt looks for things for sale or rent (a car, a "
    "flat, a laptop, tickets, a hotel room) and shows offers with prices. A local service looks for a business "
    "near him to call or visit (a plumber, a barber, a restaurant, a doctor). Pictures show photos. The browser "
    "is for a site he NAMED or an account he must be logged into. A brain worker is a long comparison that has "
    "to be parsed and filtered across sources (insurance quotes, broadband plans, a shortlist with criteria)."
)

CHOICE = {
    INLINE_FACT: "one fact or a short answer looked up now: a time, the weather, a price of one known thing, who "
                 "won, how to, ideas or suggestions he can hear in a sentence or two",
    LISTING: "things for sale or rent to choose among, with prices: a product, a vehicle, a home, a hotel room, "
             "tickets, a rental car",
    LOCAL_SERVICE: "a business or professional near him to contact: plumber, barber, dentist, restaurant, shop, "
                   "with phone, rating or availability",
    IMAGES: "pictures or photos to look at",
    BROWSER: "a specific website he named, or something behind his own login, that has to be opened and driven",
    BRAIN_WORKER: "a long comparison across sources with several criteria to parse and filter: insurance quotes, "
                  "phone or broadband plans, a researched shortlist, a plan for a weekend",
}


def question() -> dict:
    """The brief question, in the shape `nucleo/jev.py::ask_many` takes (`{instructions, criteria}`)."""
    return {"instructions": INSTRUCTIONS, "criteria": dict(CHOICE)}


#: The model's tool → the module it proposes. `web_search` is deliberately absent: it is refined below.
_PROPOSAL = {"search_listings": LISTING, "show_images": IMAGES, "escalate_to_slowbrain": BRAIN_WORKER}
#: The tools that ARE a search. Anything else (`play_video`, `play_music`, a data-op…) never consults this module:
#: a video request goes to the player, not to the sheet, and the bank says so.
SEARCH_PROPOSALS = frozenset({"web_search", *_PROPOSAL})


def is_search_proposal(proposal: str) -> bool:
    return str(proposal or "").strip() in SEARCH_PROPOSALS


@dataclass
class Route:
    module: str
    why: str
    confidence: float
    breadth: dict = field(default_factory=dict)
    fields: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"module": self.module, "why": self.why, "confidence": round(float(self.confidence), 2),
                "breadth": dict(self.breadth), "fields": list(self.fields)}


def _read(verdicts: dict | None, key: str) -> tuple[str, float]:
    """`(choice, confidence)` from a verdict map whose values are `choice`, `(choice, conf)` or `{choice, confidence}`."""
    v = (verdicts or {}).get(key)
    if v is None:
        return "", 0.0
    if isinstance(v, dict):
        return str(v.get("choice") or ""), float(v.get("confidence") or 0.0)
    if isinstance(v, (tuple, list)) and len(v) >= 2:
        return str(v[0] or ""), float(v[1] or 0.0)
    return str(v), 1.0


def search_route(request: str, *, proposal: str = "", verdicts: dict | None = None,
                 judge: Callable[[str, dict], tuple[str, float]] | None = None,
                 named_site: bool = False) -> Route:
    """ONE module for this request.

    `proposal` — the tool the model called (`web_search`, `search_listings`, `show_images`,
    `escalate_to_slowbrain`) or "".
    `verdicts` — the brief's answers: `search_module`, `escalate_or_inline`, `errand_surface`, each as
    `(choice, confidence)` or `{choice, confidence}`.
    `judge` — optional `fn(request, question) -> (choice, confidence)`; asked ONCE, only when the brief did not
    carry the routing verdict and the proposal does not settle it.
    `named_site` — the request names a website or an account (read by the caller from its own evidence)."""
    crit = _criteria.for_request(request)
    breadth = {k: crit[k] for k in ("n_final", "min_candidates", "said")}
    fields = list(crit["fields"])

    def _route(module: str, why: str, conf: float) -> Route:
        if named_site and module in (LISTING, LOCAL_SERVICE, BRAIN_WORKER, INLINE_FACT):
            return Route(BROWSER, f"he named a site — {why}", max(conf, SURE), breadth, fields)
        return Route(module, why, conf, breadth, fields)

    choice, conf = _read(verdicts, SEARCH_KEY)
    if choice in MODULES and conf >= SURE:
        return _route(choice, "the brief's routing verdict, sure", conf)

    proposed = _PROPOSAL.get(str(proposal or "").strip(), "")
    if proposed:
        if choice in MODULES and conf >= FLOOR and choice != proposed:
            # The verdict COMPLETES the model: an unsure verdict does not overturn a module the model named.
            return _route(proposed, f"the model proposed it (verdict {choice} at {conf:.2f} did not reach {SURE})", 0.7)
        return _route(proposed, "the model proposed it", 0.8)

    if choice in MODULES and conf >= FLOOR:
        return _route(choice, "the brief's routing verdict, unsure but unopposed", conf)

    if judge is not None and not choice:
        try:
            jc, jconf = judge(request, question())
        except Exception:  # noqa: BLE001 — a judge that fails leaves the local decision untouched
            jc, jconf = "", 0.0
        if jc in MODULES and jconf >= FLOOR:
            return _route(jc, "asked the judge once", jconf)

    # Nothing named the module: the escalate verdict and the surface complete a generic search.
    esc, esc_conf = _read(verdicts, "escalate_or_inline")
    surface, _ = _read(verdicts, "errand_surface")
    if esc == "escalate" and esc_conf >= SURE and surface in ("lista", "item", "list", "results"):
        return _route(BRAIN_WORKER, "a sure escalation whose deliverable is a sheet", esc_conf)
    if esc == "handle_inline" and esc_conf >= SURE:
        return _route(INLINE_FACT, "a sure handle_inline verdict", esc_conf)
    if str(proposal or "").strip() == "web_search":
        return _route(INLINE_FACT, "the model asked for a web search and nothing says it is a commission", 0.6)
    return _route(INLINE_FACT, "default: nothing read as a commission", 0.5)
