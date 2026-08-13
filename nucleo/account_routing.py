#
# ACCOUNT SESSION ROUTING (2026-08-09) — fly-replay support for real, persistent account Machines:
# `zaelar-accounts` is ONE Fly app with MANY Machines (one per user), all sharing one public
# hostname — Fly's edge picks whichever is available for a plain request, not necessarily the
# visitor's OWN one. Fix: whichever Machine picks up a request first tells Fly's proxy "replay this
# on machine X" via the `fly-replay` response header.
#
# An account Machine's identity is FIXED forever (no warm-pool pinning needed). The routing key
# carried by the browser (the zaelar_cloud_session cookie) is an OPAQUE session token — resolving
# "which Fly Machine does this token belong to" means asking the control-plane (POST /session/verify,
# which already returns the account's `fly_machine_id`). `FLY_MACHINE_ID` — this Machine's OWN id —
# is injected automatically by Fly on every Machine, so "is this request mine?" is a plain string
# compare, no lookup needed for the common case (only a MISROUTED request pays the control-plane
# round-trip).
#
# A Machine that isn't an account Machine at all (ZAELAR_USER_ID unset — self-host) never enters any
# of this — my_machine_id() below is only ever consulted when cloud_account.is_cloud_account() is
# True.
#
# 2026-08-13 — RESOLUTION IS NOW A THREE-WAY ANSWER, NOT AN OPTIONAL STRING. `find_machine_for_session`
# returned `None` both for "the resolver says this token is not a live session" and for "we could not
# ask the resolver at all", and its only caller read that `None` as permission to serve the request
# locally. Those are opposite facts: the first is a decision, the second is the ABSENCE of one, and a
# timeout is not an authorization. `resolve_session_machine` keeps them apart (RESOLVED / NO_SESSION /
# UNAVAILABLE) so the caller can refuse instead of guessing — see server/ingress.py.
#
import asyncio
import os
import time

import httpx
from loguru import logger

SESSION_COOKIE = "zaelar_cloud_session"

# Resolution outcomes. `RESOLVED` carries a machine id; the other two never do.
RESOLVED = "resolved"          # the resolver answered and this token belongs to a known machine
NO_SESSION = "no_session"      # the resolver answered: this token is not a live session
UNAVAILABLE = "unavailable"    # we could not obtain an answer (not configured, network, timeout, 4xx/5xx)


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() not in ("", "0", "false", "no")


def is_account_routing_machine() -> bool:
    """True on any Machine that should PARTICIPATE in account routing — a real account Machine
    (ZAELAR_USER_ID set) OR the always-on base "router" (ZAELAR_ACCOUNT_ROUTER=1). Without the
    router flag, a request that lands on the base Machine (which has no account identity of its
    own) would just serve its OWN generic content instead of ever attempting a fly-replay — found
    live 2026-08-09: the base Machine answered a cookie meant for a different account's Machine,
    silently, because nothing told it to even TRY routing."""
    from nucleo import cloud_account

    if cloud_account.is_cloud_account():
        return True
    return _truthy("ZAELAR_ACCOUNT_ROUTER")

# session_token -> (outcome, fly_machine_id|None, cached_at). A session token's owning Machine is
# STABLE for the token's lifetime — avoids a resolver round-trip on every request.
#
# A NEGATIVE answer is cached too, but for far less time: without it an unrecognised token (a stale
# cookie, or a probe hammering the endpoint) buys one round-trip per request and turns this process
# into an amplifier against the resolver. It has to stay short, because "not a session" becomes
# "a session" the moment the visitor logs in and reuses the same jar.
#
# An UNAVAILABLE answer is NEVER cached: it says nothing about the token, only about the network at
# that instant, and caching it would extend one blip into minutes of refusals.
_TOKEN_MACHINE_CACHE: dict[str, tuple[str, str | None, float]] = {}
_CACHE_TTL = 300.0
_NEGATIVE_CACHE_TTL = 20.0

_INFLIGHT: dict[str, "asyncio.Future"] = {}


def my_machine_id() -> str | None:
    """This Machine's own Fly id — auto-injected by the Fly runtime, not something we set."""
    return (os.getenv("FLY_MACHINE_ID") or "").strip() or None


def resolver_headers() -> dict[str, str]:
    """Credential for the configured resolver endpoint, when one is configured. The endpoint may
    require the caller to be a known workload rather than anyone who can reach its URL; without a
    configured credential this is empty and the request goes out unauthenticated (which such an
    endpoint is then free to reject)."""
    token = (os.getenv("CONTROL_PLANE_SERVICE_TOKEN") or "").strip()
    return {"X-Service-Token": token} if token else {}


def _cache_get(token: str) -> tuple[str, str | None] | None:
    hit = _TOKEN_MACHINE_CACHE.get(token)
    if not hit:
        return None
    outcome, machine_id, at = hit
    ttl = _CACHE_TTL if outcome == RESOLVED else _NEGATIVE_CACHE_TTL
    if (time.monotonic() - at) < ttl:
        return outcome, machine_id
    return None


def _cache_put(token: str, outcome: str, machine_id: str | None) -> None:
    if outcome == UNAVAILABLE:
        return
    _TOKEN_MACHINE_CACHE[token] = (outcome, machine_id, time.monotonic())


def _reset_cache_for_tests() -> None:
    _TOKEN_MACHINE_CACHE.clear()
    _INFLIGHT.clear()


async def resolve_session_machine(
    session_token: str, *, control_plane_url: str, timeout: float = 3.0
) -> tuple[str, str | None]:
    """Resolve a session token to the machine id that owns it, as a THREE-WAY answer:

        (RESOLVED, "<machine id>")  the resolver identified the owning machine
        (NO_SESSION, None)          the resolver answered, and this token is not a live session
        (UNAVAILABLE, None)         no answer was obtained — say so, never invent one

    Cached + single-flighted. Never raises: a failure is reported as UNAVAILABLE, which the caller
    must treat as "I do not know", not as "go ahead"."""
    if not control_plane_url:
        return UNAVAILABLE, None

    cached = _cache_get(session_token)
    if cached is not None:
        return cached

    inflight = _INFLIGHT.get(session_token)
    if inflight is not None:
        try:
            return await inflight
        except Exception:  # noqa: BLE001
            return UNAVAILABLE, None

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    _INFLIGHT[session_token] = fut
    try:
        result = await _lookup_machine(
            session_token, control_plane_url=control_plane_url, timeout=timeout
        )
        _cache_put(session_token, result[0], result[1])
        if not fut.done():
            fut.set_result(result)
        return result
    except Exception as e:  # noqa: BLE001
        # Deliberately logs the EXCEPTION CLASS and not the token: a session token is a credential.
        logger.warning(f"account_routing: session lookup unavailable ({type(e).__name__})")
        if not fut.done():
            fut.set_result((UNAVAILABLE, None))
        return UNAVAILABLE, None
    finally:
        _INFLIGHT.pop(session_token, None)


async def _lookup_machine(session_token, *, control_plane_url, timeout) -> tuple[str, str | None]:
    url = control_plane_url.rstrip("/") + "/session/verify"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(
            url, json={"session_token": session_token}, headers=resolver_headers()
        )
    # A rejection of OUR credential (401/403) is not a statement about the visitor's session — it
    # means this process cannot ask. Reporting it as NO_SESSION would lock every visitor out on a
    # credential mistake; reporting it as UNAVAILABLE makes it a visible outage instead of a silent
    # mass 401. Same for 5xx.
    if res.status_code >= 400:
        logger.warning(f"account_routing: resolver returned {res.status_code}")
        return UNAVAILABLE, None
    data = res.json()
    if not data.get("loggedIn"):
        return NO_SESSION, None
    machine_id = (data.get("machine") or {}).get("fly_machine_id")
    if not machine_id:
        # A live session whose account has no machine on record. Not this process's to serve.
        return NO_SESSION, None
    return RESOLVED, machine_id
