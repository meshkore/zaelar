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
def _is_free(agent: dict, card: dict | None = None) -> bool:
    """True only when the price is unambiguously zero.

    Unknown counts as NOT free, on purpose. The operator's instruction is "I am fine with using free
    agents», and the failure modes are not symmetric: skipping a free agent we could not price costs one
    fallback to the browser, while calling a paid one costs money nobody authorised.
    """
    for src in (agent, card or {}):
        pricing = (src or {}).get("pricing") or ((src or {}).get("agent_card") or {}).get("pricing") or {}
        if not isinstance(pricing, dict):
            continue
        amount, currency = pricing.get("amount"), str(pricing.get("currency") or "").lower()
        if amount is not None:
            try:
                return float(amount) == 0.0
            except (TypeError, ValueError):
                return False
        if currency in ("free", "none"):
            return True
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
    """
    query = (query or "").strip()
    if not query:
        return {"intent": "", "agents": []}
    status, data = _post(f"{ORACLE_URL}/v1/search",
                         {"prompt": query, "query": query, "source": "mesh", "audience": "personal",
                          "filters": {"limit": max(1, int(limit)), "online_only": True}})
    if status != 200 or not isinstance(data, dict):
        return {"intent": "", "agents": []}
    agents = [a for a in (data.get("agents") or []) if isinstance(a, dict) and _is_live(a) and _endpoint_of(a)]
    if free_only:
        agents = [a for a in agents if _is_free(a) or _is_free(a, _card_of(_endpoint_of(a)))]
    return {"intent": str(data.get("intent") or ""), "query_id": data.get("query_id"), "agents": agents}


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
_HINT_KEYS = ("error", "detail", "need", "needs", "missing", "required", "message", "hint")


def _what_the_agent_asks_for(data) -> dict:
    """The actionable part of an error response, without dragging the entire body into the worker's context."""
    if not isinstance(data, dict):
        return {}
    return {k: data[k] for k in _HINT_KEYS if data.get(k) not in (None, "", [], {})}


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
    found = find(errand)
    intent, agents = found.get("intent") or "", found.get("agents") or []
    cached = route_for(intent) if intent else None
    if cached:
        agents = [cached] + [a for a in agents if a.get("agent_id") != cached.get("agent_id")]
    if not agents:
        return {"ok": False, "reason": "no hay ningún agente libre en la red para esto", "intent": intent}
    dijo: dict = {}
    quien = ""
    for agent in agents[:2]:            # one retry with the next candidate; beyond that the browser is faster
        res = ask(agent, prompt, fields)
        if res.get("ok"):
            remember_route(intent, agent)                    # a no-op for an intent that cannot key a route
            return {"ok": True, "intent": intent, "agent": agent.get("agent_id"), "data": res.get("data")}
        if res.get("payment_required"):
            return {"ok": False, "reason": f"«{agent.get('agent_id')}» cobra por esto", "intent": intent}
        if not dijo and res.get("asks"):
            dijo, quien = res["asks"], str(agent.get("agent_id") or "")
    # V2-487: an agent that answers 400 by saying WHAT it lacks DID answer. Saying "they did not answer" here
    # is what sent the errand to the browser when the answer was one field away.
    if dijo:
        return {"ok": False, "intent": intent, "agent": quien, "agent_asks": dijo,
                "reason": f"«{quien}» no acepta el encargo en texto libre y dice qué necesita "
                          f"(ver `agent_asks`): vuelve a pedírselo con `--field clave=valor`"}
    return {"ok": False, "reason": "los agentes de la red no contestaron", "intent": intent}
