"""mesh_agents.py — ask the open MeshKore mesh whether some OTHER agent already does this task.

A browser is how zaelar does a web errand when nothing better exists. It is not the *good* way: it is the
last resort. Driving a real Chromium through a booking site means fighting the exact defences those sites
deploy against automation — a measured run spent its whole life on Booking's `chal_t=` anti-bot challenge,
another walked into Google's CAPTCHA — and even when it works it costs minutes of a conversation.

The mesh already has agents that serve those same domains over plain HTTP. Verified live against the public
Oracle while writing this module: one `POST /v1/search` for "hotel en Madrid esta noche" returns `roomrover`
(online, **free**), and one `POST` to its endpoint with explicit dates returns 10 real properties with
booking links — no browser, no challenge, about a second.

## What this module is NOT

It is **not a catalogue of plugins**. There is no list of known providers anywhere in this file, and adding
support for flights or tickets or restaurants requires no edit here: the Oracle is asked at the moment the
task is planned, and whatever is live and free that day is what comes back. A
static list would be stale the first time a publisher deployed something new, and would have to be curated
by us forever.

What IS remembered is the ROUTE — «for this kind of errand, this agent answered» — keyed by the intent the
Oracle itself resolved. That is the same idea as `nucleo/flash/site_catalog.py`'s genetics for websites: the
first errand of a kind pays the discovery, the next ones go straight there. It is a cache, so it expires and
it is never the only way to find an agent.

## Money

Free agents only, and that is enforced here rather than left to a prompt: `_is_free` reads the price the
Oracle (or the agent's own card) reports, and anything that is not unambiguously zero is dropped. A `402
Payment Required` challenge is returned to the caller as a fact, never paid, never retried. When paid agents
become a product decision, this is the single place that changes.

## Gotchas, all verified live and all previously paid for by `integrations/openclaw-plugin`

  · the free-text field is **`prompt`**, not `query`, on BOTH hops. A real agent given a well-formed
    `{"query": …}` answers `400 missing_fields`, which at least says so. The Oracle instead answers
    *something* — a BM25 keyword match — so `{"query": "vuelo de Madrid a Roma"}` comes back 200 with zero
    agents and reads exactly like «the mesh has nobody for this». It has aerocast. Both fields are sent.
  · the Oracle's result carries a bare `endpoint` and no usable card, so the skill PATH is read from the
    agent's own `/.well-known/agent.json` — and only its PATHNAME. The host advertised there can be a
    hostname with no DNS record at all, while the origin the Oracle verified serves the same path fine.
  · **an agent's own date parsing cannot be trusted**: asked for «esta noche» on 2026-08-19, roomrover
    resolved check-in to 2025-06-21 and returned nothing. Relative dates are resolved by the CALLER and sent
    as explicit ISO dates, which is what turned 0 results into 10.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from loguru import logger

ORACLE_URL = "https://meshkore-oracle.rjj.workers.dev"
USER_AGENT = "zaelar-mesh-client/1.0"
_TIMEOUT_S = 12.0
_CARD_TIMEOUT_S = 5.0          # an optimisation must never dominate the budget of what it optimises
_DEFAULT_SKILL_PATH = "/v1/search"
_ROUTE_TTL_S = 7 * 24 * 3600   # a learned route is a shortcut, not a truth: it expires
_KV_ROUTES = "mesh:routes"


def _post(url: str, body: dict, timeout: float = _TIMEOUT_S,
          bearer: str | None = None) -> tuple[int, dict | None]:
    """POST JSON, return (status, parsed). Never raises: a mesh that is down must degrade to the browser."""
    headers = {"content-type": "application/json", "user-agent": USER_AGENT}
    if bearer:
        headers["authorization"] = f"Bearer {bearer}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "null")
    except urllib.error.HTTPError as e:                      # 402 and friends carry a body worth reading
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "null")
        except Exception:
            return e.code, None
    except Exception as e:                                   # noqa: BLE001
        logger.debug(f"mesh: POST {url} falló: {e}")
        return 0, None


def _get(url: str, timeout: float = _CARD_TIMEOUT_S) -> dict | None:
    req = urllib.request.Request(url, headers={"user-agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "null")
    except Exception:
        return None


# ── pricing ──────────────────────────────────────────────────────────────────────────────────────────────
def _tier_is_free(tier: dict) -> bool | None:
    """One pricing entry: True free, False priced, None it did not say."""
    if not isinstance(tier, dict):
        return None
    amount, currency = tier.get("amount"), str(tier.get("currency") or "").lower()
    if amount is not None:
        try:
            return float(amount) == 0.0
        except (TypeError, ValueError):
            return False
    return True if currency in ("free", "none") else None


def _is_free(agent: dict, card: dict | None = None) -> bool:
    """True only when the price is unambiguously zero.

    Unknown counts as NOT free, on purpose. The operator's instruction is "I am fine with using free
    agents», and the failure modes are not symmetric: skipping a free agent we could not price costs one
    fallback to the browser, while calling a paid one costs money nobody authorised.

    V2-593 · `pricing` may be a LIST of tiers, and an agent is free when ANY tier is unambiguously zero.
    That is not a loosening of the rule, it is the shape the rule now arrives in: after the operator ruled
    that every agent Zaelar can use must have a free tier, the agents that had one published it as
    «free tier + paid tiers», and a single-dict reader is blind to exactly the thing it is looking for —
    measured 2026-09-05, `lucid` and `ybana` published `amount: 0` as their first tier and this returned
    False for both.

    What keeps it safe is unchanged and is not this function: **the motor never pays**. Exhausting a free
    quota returns `402`, and `ask()` reports a 402 as a fact and never pays it, never retries it. So the
    worst case of calling a tiered agent is an errand that falls back to the browser — never a charge.
    """
    for src in (agent, card or {}):
        pricing = (src or {}).get("pricing") or ((src or {}).get("agent_card") or {}).get("pricing")
        if isinstance(pricing, dict):
            verdict = _tier_is_free(pricing)
            if verdict is not None:
                return verdict
        elif isinstance(pricing, list) and pricing:
            verdicts = [_tier_is_free(t) for t in pricing]
            if any(v is True for v in verdicts):
                return True
            if any(v is False for v in verdicts):
                return False               # priced tiers and not one free: that is a NO, not a «did not say»
    return False


def _is_live(agent: dict) -> bool:
    if agent.get("online") is False:
        return False
    return str(agent.get("status") or "available").lower() in ("available", "online", "active", "")


def _endpoint_of(agent: dict) -> str:
    """The Oracle puts `endpoint` top-level for some agents and under the card for others — check both."""
    card = agent.get("agent_card") or {}
    return str(agent.get("endpoint") or (card.get("contact") or {}).get("http") or card.get("endpoint") or "")


def _bearer_for(agent: dict, endpoint: str) -> str | None:
    """A mesh agent may gate its skills behind a bearer of its own issue (e.g. to cap the provider bill its
    calls run up). The credential, when this deployment holds one, lives in the credentials store under
    `MESH_BEARER_<AGENT_ID>` — agent id uppercased, runs of non-alphanumerics collapsed to `_` — with the
    endpoint HOST tried under the same scheme as fallback. No entry, no header: agents that never asked for
    auth keep being called exactly as before, and the token itself never appears in code, prompts or logs."""
    try:
        from config import credentials
    except Exception:                                        # noqa: BLE001 — no store, no bearer
        return None
    for raw in (agent.get("agent_id"), urllib.parse.urlparse(endpoint).hostname):
        if not raw:
            continue
        key = "MESH_BEARER_" + re.sub(r"[^A-Za-z0-9]+", "_", str(raw)).strip("_").upper()
        try:
            val = credentials.get(key)
        except Exception:                                    # noqa: BLE001
            val = ""
        if val:
            return val
    return None


# ── discovery ─────────────────────────────────────────────────────────────────────────────────────────────
def find(query: str, *, limit: int = 5, free_only: bool = True) -> dict:
    """Ask the Oracle, in the operator's own words, who can serve this errand.

    Returns `{"intent": str, "agents": [...], "query_id": ...}`; `agents` is empty when nobody can, which is
    a perfectly ordinary answer and means the browser stays the plan.

    **The errand goes in `prompt`, and that is not cosmetic — it is what turns the parser on.** The Oracle
    has two modes and picks by field: `query` alone is a BM25 keyword match over the catalogue, while
    `prompt` runs its own NL parse first. Keyword matching an English catalogue with Spanish words finds
    nothing, which is exactly the shape of a language problem and is not one. Measured the same minute,
    2026-08-19:

        {"query":  "vuelo de Madrid a Roma"}  -> intent `general`,          0 agents
        {"prompt": "vuelo de Madrid a Roma"}  -> intent `bookings.flights`, aerocast + parsed MAD->FCO
        {"prompt": "entradas de teatro en Madrid"} -> ticketlumen (free, 10 real events)

    So the upstream skill doc is right that the operator's verbatim words are the thing to send; what it does
    not say is that they only reach the parser through `prompt`. Both fields are sent.

    And check what comes back: the mapping is loose at the edges (an English restaurant query returns
    `roomrover`, a hotel agent). An agent that answers the wrong domain is a fallback to the browser, not a
    result.

    V2-581 · Since 2026-09-05 the Oracle can do that check on its side, and is asked to:

    - **`strict: true`** makes it return NOTHING rather than a category-mismatched agent. This is the
      request this module made after measuring a TRAIN errand answered with ten FLIGHT offers: zero is
      better than wrong, because zero falls back to the browser and a false positive hands the user a lie.
    - **`domain_match`** on each row and **`coverage`** on the envelope. `domain_match: false` is dropped
      here too — belt and braces, because `strict` is the server's promise and this is ours.
    - **`free` / `pricing` now travel in the row**, so pricing an agent no longer costs a card fetch per
      candidate on the critical path. `_is_free` already reads the row; the card lookup below is now the
      rare fallback it was always meant to be.

    None of this makes the caller's own check optional. Measured the same day, WITH strict on: «find a flat
    to rent in Madrid under 1200 EUR» comes back `coverage: full`, `domain_match: true` — and the agent is
    `ebay-finder`, which answers `ok: true` with nine eBay listings whose top hit is a *«PISO EN ALQUILER»
    banner sign* for €81. The label makes that lie more credible, not less. `serve` returning `serves`
    (V2-580) is what lets the caller catch it.
    """
    query = (query or "").strip()
    if not query:
        return {"intent": "", "agents": [], "reached": False}
    status, data = _post(f"{ORACLE_URL}/v1/search",
                         {"prompt": query, "query": query, "source": "mesh", "audience": "personal",
                          "strict": True,
                          "filters": {"limit": max(1, int(limit)), "online_only": True}})
    if status != 200 or not isinstance(data, dict):
        # V2-594 · `reached` separates «the Oracle answered and has nobody» from «the Oracle did not answer».
        # Flattening those two is the same mistake V2-487 fixed one layer down: both look like an empty list,
        # and only one of them is worth remembering. Caching a network outage would turn one bad minute into
        # three bad days.
        return {"intent": "", "agents": [], "reached": False}
    agents = [a for a in (data.get("agents") or []) if isinstance(a, dict) and _is_live(a) and _endpoint_of(a)]
    # An explicit `false` is a statement; a missing key is an older Oracle that never made one. Only the
    # statement is acted on — treating silence as a mismatch would empty the mesh the day it is rolled back.
    agents = [a for a in agents if a.get("domain_match") is not False]
    if free_only:
        agents = [a for a in agents if _is_free(a) or _is_free(a, _card_of(_endpoint_of(a)))]
    return {"intent": str(data.get("intent") or ""), "query_id": data.get("query_id"),
            "coverage": str(data.get("coverage") or ""), "agents": agents, "reached": True}


_cards: dict[str, dict | None] = {}


def _card_of(endpoint: str) -> dict | None:
    """The agent's own A2A card, fetched once per origin. Best-effort: no card is not an error."""
    if endpoint not in _cards:
        _cards[endpoint] = _get(f"{endpoint.rstrip('/')}/.well-known/agent.json")
    return _cards[endpoint]


def _skill_path(endpoint: str) -> str:
    """Where this agent serves. Only the PATH comes from the card — never its host (see the module docstring:
    an advertised host with no DNS record would turn a reachable agent into a network failure)."""
    from urllib.parse import urlparse
    if urlparse(endpoint).path not in ("", "/"):
        return ""                                            # the endpoint already names its path
    card = _card_of(endpoint) or {}
    advertised = ((card.get("contact") or {}).get("http")) or ""
    try:
        path = urlparse(advertised).path
    except Exception:
        path = ""
    return path if path and path != "/" else _DEFAULT_SKILL_PATH


# V2-487 · what the agent ANSWERS when it says no, measured on 2026-08-29 against `roomrover` live:
#
#     POST /v1/search {"prompt": "hotel in New York City check-in 2026-09-10 …"}
#       → 400 {"error": "parse_failed", "detail": "Oracle parser did not return constraints.
#                        Pass structured fields (city, checkin, checkout) instead."}
#     POST /v1/search {"city": "New York", "checkin": "2026-09-10", "checkout": "2026-09-12", "adults": 2}
#       → 400 {"error": "missing_fields", "need": ["country_code"]}
#     …with `country_code: "US"` → **200 with ten real New York hotels**, price, rating, and booking link,
#       in 0.4 s and without a browser.
#
# In other words: the agent was not silent; it was telling us HOW to ask it — and this `ask` flattened that to
# "returned 400", which `serve` flattened again to "the network agents did not answer". That statement is a
# FALSE diagnosis, and an expensive one: it sends the worker to open Chromium against Booking for data that
# was one field away. The exact form is stated by the module's own docstring ("answers 400 missing_fields,
# which at least says so") — it was known, yet still discarded.
#
# The field is passed through, not guessed: there is NO hotel or flight schema here. The agent declares what it
# needs, and the worker —which has the errand and does the reasoning— composes it. This is the same contract as
# the rest of the module: no catalogue, no provider list, nothing to curate forever.
# Two DIFFERENT things arrive in an error body and they must not be confused. `_NEED_KEYS` are the agent
# saying «give me these fields and I can serve you» — actionable, and the caller can retry. `_DIAG_KEYS` are
# the agent saying «something broke» — worth repeating to the operator, worthless to retry on. V2-487 kept
# them in one tuple, so an upstream 422 was reported to the caller as a request for fields and the honest
# advice «ask again with --field key=value» was given for an errand that already HAD every field. Measured
# against `aerocast` on 2026-09-05: it fails roughly half the time on a relative date, and every one of those
# failures was dressed up as a missing-field prompt.
_NEED_KEYS = ("need", "needs", "missing", "required")
_DIAG_KEYS = ("error", "detail", "message", "hint")
_HINT_KEYS = _NEED_KEYS + _DIAG_KEYS
_DIAG_MAX = 300


def _what_the_agent_asks_for(data) -> dict:
    """The actionable part of an error response, without dragging the entire body into the worker's context."""
    if not isinstance(data, dict):
        return {}
    out = {}
    for k in _HINT_KEYS:
        v = data.get(k)
        if v in (None, "", [], {}):
            continue
        # A diagnostic often carries the upstream's whole body (a Duffel 422 measured at 400+ chars). It is
        # kept because it names the real cause, but it is NOT allowed to become the caller's context.
        if k in _DIAG_KEYS and isinstance(v, str) and len(v) > _DIAG_MAX:
            v = v[:_DIAG_MAX] + "…"
        out[k] = v
    return out


# «I am missing a field» does not always arrive under a field-shaped key. Measured against `ybana`, which
# answers 400 with `{"error": "missing_product", "detail": "body.product is required"}` — actionable, and
# invisible to a check that only looks at `need`/`missing`/`required` AS KEYS. V2-596 split the keys and, in
# doing so, started reporting this exact shape as «the agent broke, more data will not help», which is the
# opposite of true. The wording is what separates the two cases: a MISSING field is announced as missing or
# required, while a broken upstream describes what it received as invalid — Duffel's 422 says «Field
# 'departure_date' is invalid», never that it is absent.
_MISSING_WORDING = re.compile(r"\bmissing[_\s-]|\b(?:is|are)\s+required\b|\brequired\b.*\bfield\b", re.I)


def _names_missing_fields(asks: dict) -> bool:
    """True when the agent said WHICH field it lacks — the one case where retrying with `fields` helps."""
    if any(asks.get(k) not in (None, "", [], {}) for k in _NEED_KEYS):
        return True
    return any(isinstance(asks.get(k), str) and _MISSING_WORDING.search(asks[k]) for k in _DIAG_KEYS)


def ask(agent: dict, prompt: str, fields: dict | None = None) -> dict:
    """Put the errand to one agent. Returns `{ok, data|error|payment_required}` — never raises, never pays.

    `prompt` must carry ABSOLUTE dates and the concrete details: an agent's own resolution of «esta noche» is
    not something to rely on (measured: it answered with a check-in from the previous year and zero results).

    `fields` are the agent's OWN structured parameters, straight through. Nothing here knows what any of them
    mean, and that is the point — see the note above `_HINT_KEYS`.
    """
    endpoint = _endpoint_of(agent)
    if not endpoint:
        return {"ok": False, "error": "el agente no publica un endpoint HTTP"}
    url = endpoint.rstrip("/") + _skill_path(endpoint)
    # Either free text OR fields, NEVER both — measured against `roomrover` on 2026-08-29. With `prompt` present
    # the agent takes its natural-language path and **discards the fields**: the same body that returns ten
    # hotels without `prompt` returns `parse_failed` with it included. "Explicit data wins over free text" was
    # my assumption about the agent's precedence, and it was false; this is what was measured.
    body = {str(k): v for k, v in (fields or {}).items()} or {"prompt": prompt, "query": prompt}
    # Bearer only when the store holds one for THIS agent — passed as keyword and only then, so callers (and
    # test doubles) that know nothing about auth keep their `(url, body)` shape working unchanged.
    bearer = _bearer_for(agent, endpoint)
    status, data = _post(url, body, bearer=bearer) if bearer else _post(url, body)
    if status == 402:
        # A charge is a decision for the operator, and this build only uses free agents anyway. Reported as a
        # fact so the caller can say so, never held and never paid.
        return {"ok": False, "payment_required": True, "challenge": data, "agent": agent.get("agent_id")}
    if status != 200:
        asks = _what_the_agent_asks_for(data)
        return {"ok": False, "status": status, "asks": asks,
                "error": f"{agent.get('agent_id') or url} respondió {status or 'nada'}",
                "agent": agent.get("agent_id")}
    return {"ok": True, "agent": agent.get("agent_id"), "endpoint": url, "data": data}


# ── the genetic part: the learned route ───────────────────────────────────────────────────────────────────
def _routes() -> dict:
    try:
        from memory import api as memory
        return memory.kv_get(_KV_ROUTES, {}) or {}
    except Exception:
        return {}


# The Oracle's bucket for «I could not classify this». It is not a kind of errand, so it cannot key a route:
# caching under it would send every unclassified errand — a plumber, a bicycle — to whichever agent happened
# to answer a theatre query once. Measured: «entradas de teatro en Madrid» resolves to `general` and still
# returns `ticketlumen`, so this is the normal case and not a corner one.
_UNCACHEABLE = ("", "general", "unknown", "other")


def _cacheable(intent: str) -> bool:
    return str(intent or "").strip().lower() not in _UNCACHEABLE


def route_for(intent: str) -> dict | None:
    """The agent that already served this kind of errand, if one did and the memory has not expired.

    Same shape of shortcut as `site_catalog`'s website-per-category, and for the same reason the operator
    gave: the first flight search may take longer, the next one should not repeat the discovery. It is a
    CACHE — it expires, and `find()` is always still there — so a publisher that disappears costs one failed
    call, not a permanently wrong route.
    """
    if not _cacheable(intent):
        return None
    r = (_routes() or {}).get(str(intent or ""))
    if not isinstance(r, dict):
        return None
    if time.time() - float(r.get("at") or 0) > _ROUTE_TTL_S:
        return None
    return r.get("agent") if isinstance(r.get("agent"), dict) else None


def remember_route(intent: str, agent: dict) -> None:
    """Record that this agent served this intent. Only ever called after a REAL successful answer."""
    intent = str(intent or "").strip()
    if not _cacheable(intent) or not isinstance(agent, dict) or not _endpoint_of(agent):
        return
    try:
        from memory import api as memory
        routes = _routes()
        routes[intent] = {"at": time.time(),
                          "agent": {"agent_id": agent.get("agent_id"), "endpoint": _endpoint_of(agent),
                                    "capabilities": agent.get("capabilities") or []}}
        memory.kv_set(_KV_ROUTES, routes)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"mesh: no pude recordar la ruta de {intent}: {e}")


# V2-580 · The Oracle ranks a category-mismatched agent first and the agent answers it CONFIDENTLY. Measured
# 2026-09-05: asked for a TRAIN Madrid→Barcelona, the Oracle offered `aerocast` (flights) and `aerocast`
# returned `ok: true` with ten FLIGHT offers. The failure arrives green — not a 404, not an empty list, a 200
# with ten plausible, well-formed, wrong results.
#
# The module docstring already says checking the domain of what comes back is part of the contract, and the
# worker prompt says it too. But `serve` handed the caller an opaque `agent` id and the payload, so the check
# it was being ordered to perform had NOTHING to perform it against: the payload of a wrong-domain answer
# looks exactly like the payload of a right one.
#
# So this does not add a taxonomy, a domain table, or a verb list — the house rule is to teach the caller, not
# to hardcode. It just stops throwing away what the agent ALREADY declares about itself, and hands it over
# next to the data. Deciding is still the caller's job; now it has the two facts it needs to decide.
_MAX_CAPS = 12
_MAX_DESC = 240


def _declares(agent: dict, card: dict | None = None) -> dict:
    """What the agent SAYS it does, trimmed for a worker's context. Never a judgement, only the claim."""
    src = agent or {}
    caps = src.get("capabilities") or (card or {}).get("capabilities") or []
    caps = [str(c) for c in caps if isinstance(c, (str, int))][:_MAX_CAPS] if isinstance(caps, list) else []
    desc = str(src.get("description") or (card or {}).get("description") or "").strip()
    if len(desc) > _MAX_DESC:
        desc = desc[:_MAX_DESC].rstrip() + "…"
    out = {}
    if caps:
        out["serves"] = caps
    if desc:
        out["describes_itself_as"] = desc
    return out


def _is_empty_payload(data) -> bool:
    """True when the agent answered successfully and returned no rows.

    Only the shapes these agents actually use are inspected; anything unrecognised counts as NOT empty, so a
    payload this function does not understand is never discarded.
    """
    if data is None:
        return True
    if not isinstance(data, dict):
        return not data if isinstance(data, (list, str)) else False
    if isinstance(data.get("count"), int) and data["count"] == 0:
        return True
    lists = [v for k, v in data.items() if isinstance(v, list)]
    return bool(lists) and all(len(v) == 0 for v in lists)


def serve(errand: str, prompt: str = "", fields: dict | None = None) -> dict:
    """Discovery + contact in one call, using the learned route first. The whole module in one verb.

    Returns `{ok, agent, data}` on success, or `{ok: False, reason}` — where `reason` is meant to be said out
    loud, because «no hay ningún agente para esto» is a useful thing for the operator to hear before zaelar
    opens a browser and spends four minutes on it.
    """
    errand = (errand or "").strip()
    prompt = (prompt or errand).strip()
    if not errand:
        return {"ok": False, "reason": "sin encargo"}
    # V2-594 · the workflow table answers BEFORE the network does. A domain the mesh is known to have nothing
    # for does not pay the Oracle round trip again, and the caller gets a FACT instead of an empty result to
    # send through a model to have the emptiness narrated back. The negative row expires, so a new agent on
    # the mesh is still discovered — it is a shortcut, not a verdict.
    try:
        from nucleo import workflows as _wf
        wplan = _wf.plan(errand)
    except Exception:
        wplan = None
    if wplan and wplan.known_empty:
        return {"ok": False, "reason": "todavía no hay ningún agente en la red para esto",
                "intent": "", "coverage": "none", "domain": wplan.domain, "from_cache": True}

    found = find(errand)
    intent, agents = found.get("intent") or "", found.get("agents") or []
    coverage = found.get("coverage") or ""
    cached = route_for(intent) if intent else None
    if cached:
        agents = [cached] + [a for a in agents if a.get("agent_id") != cached.get("agent_id")]
    if not agents:
        # V2-581: «nadie cubre todavía este vertical» and «nadie contestó» are different facts, and the
        # Oracle now distinguishes them (`coverage: none` under `strict`). Saying the first one out loud is
        # honest emptiness; it also tells the operator the browser is the plan for a REASON, not by failure.
        reason = ("todavía no hay ningún agente en la red para esto" if coverage == "none"
                  else "no hay ningún agente libre en la red para esto")
        # V2-594: and remember it, so the NEXT errand of this kind does not pay for the same round trip.
        # Only `coverage: none` is cached — the Oracle stating that nothing serves this vertical. «Nobody
        # answered» is a transient failure and caching it would turn one bad minute into three bad days.
        # Cached only when the Oracle was actually REACHED. `coverage: none` is its explicit statement that
        # the vertical is uncovered; a plain zero with no coverage field is the same fact told less clearly —
        # measured, that is what an uncovered vertical really returns, and keying on the word alone meant the
        # saving never fired where it was needed most. An unreachable Oracle is cached NEVER.
        if wplan and wplan.domain and found.get("reached"):
            try:
                from nucleo import workflows as _wf
                _wf.note_empty(wplan.domain,
                               evidence=f"oracle reached, 0 agents (coverage={coverage or '-'}, "
                                        f"intent={intent or '-'})")
            except Exception:
                pass
        return {"ok": False, "reason": reason, "intent": intent, "coverage": coverage}
    dijo: dict = {}
    quien = ""
    vacio: tuple[dict, dict] | None = None      # an `ok` with no rows, held in case nobody does better
    for agent in agents[:2]:            # one retry with the next candidate; beyond that the browser is faster
        res = ask(agent, prompt, fields)
        # An `ok` carrying NOTHING is not a served errand. Measured 2026-09-06: asked in English for
        # sneakers, `ebay-finder` answered 200 with `count: 0` (its eBay lane is a sandbox with no
        # inventory), `serve` accepted it and never reached `ybana`, which had 20 real offers. The empty
        # answer is kept as a fallback — «nobody has this» is a real result — but it does not get to end the
        # search while another candidate is still standing. This is the shape that made the whole vertical
        # look alive while returning nothing.
        if res.get("ok") and _is_empty_payload(res.get("data")) and agent is not agents[:2][-1]:
            if not vacio:
                vacio = (agent, res)
            continue
        if res.get("ok"):
            remember_route(intent, agent)                    # a no-op for an intent that cannot key a route
            # What the agent declares travels WITH the answer: the caller is told to check the domain of what
            # came back, and this is what it checks against (see the note above `_declares`).
            # The card is used only if it is ALREADY memoised — never fetched for this. The declaration is a
            # nice-to-have on the success path and must not buy itself a network round-trip with a 5 s
            # timeout, per the rule this module already states about the card: an optimisation must never
            # dominate the budget of what it optimises. (The autouse network trap caught exactly this: an
            # unconditional fetch here reddened two unrelated tests, and a learned route stored before
            # capabilities were kept would have paid it on every single cached hit.)
            declared = _declares(agent) or _declares(agent, _cards.get(_endpoint_of(agent)))
            # V2-594: a success teaches the workflow table too, keyed by the LEXICAL domain rather than the
            # Oracle intent. That matters: the intent is `general` for events, shopping and wellness, which is
            # exactly where `remember_route` cannot help — the domain key has no such hole.
            if wplan and wplan.domain:
                try:
                    from nucleo import workflows as _wf
                    _wf.learn(wplan.domain, _wf.store.CH_MESH, target=str(agent.get("agent_id") or ""),
                              evidence=f"served «{errand[:60]}»", rank=10)
                except Exception:
                    pass
            # `empty` is set on EVERY path that returns no rows, not only the held-back one: a flag that
            # depends on which candidate happened to be last is a flag a caller cannot trust.
            out = {"ok": True, "intent": intent, "agent": agent.get("agent_id"),
                   **declared, "data": res.get("data")}
            if _is_empty_payload(res.get("data")):
                out["empty"] = True
            return out
        if res.get("payment_required"):
            return {"ok": False, "reason": f"«{agent.get('agent_id')}» cobra por esto", "intent": intent}
        if not dijo and res.get("asks"):
            dijo, quien = res["asks"], str(agent.get("agent_id") or "")
    # V2-487: an agent that answers 400 by saying WHAT it lacks DID answer. Saying "they did not answer" here
    # is what sent the errand to the browser when the answer was one field away.
    if dijo:
        # Only a response that NAMES the missing fields earns the «ask again with --field» advice. Anything
        # else is the agent's own breakage, and telling the caller to retry with fields sends it round a loop
        # it cannot win — the fields were never the problem.
        if _names_missing_fields(dijo):
            return {"ok": False, "intent": intent, "agent": quien, "agent_asks": dijo,
                    "reason": f"«{quien}» no acepta el encargo en texto libre y dice qué necesita "
                              f"(ver `agent_asks`): vuelve a pedírselo con `--field clave=valor`"}
        return {"ok": False, "intent": intent, "agent": quien, "agent_asks": dijo, "agent_failed": True,
                "reason": f"«{quien}» falló al atender el encargo (ver `agent_asks`); no es cuestión de "
                          f"darle más datos"}
    if vacio:
        agent, res = vacio
        declared = _declares(agent) or _declares(agent, _cards.get(_endpoint_of(agent)))
        return {"ok": True, "intent": intent, "agent": agent.get("agent_id"), "empty": True,
                **declared, "data": res.get("data")}
    return {"ok": False, "reason": "los agentes de la red no contestaron", "intent": intent}
