#
# ACCOUNT SESSION ROUTING (2026-08-09, unifying demo↔account — Fase 2) — fly-replay support for
# real, persistent account Machines. Same problem demo_routing.py solves for ephemeral demo
# Machines: `zaelar-accounts` is ONE Fly app with MANY Machines (one per user), all sharing one
# public hostname — Fly's edge picks whichever is available for a plain request, not necessarily
# the visitor's OWN one. Same fix: whichever Machine picks up a request first tells Fly's proxy
# "replay this on machine X" via the `fly-replay` response header.
#
# Simpler than demo_routing.py in one way, different in another:
#   - No warm-pool "pin on first request" dance — an account Machine's identity is FIXED forever.
#   - BUT the routing key carried by the browser (the zaelar_cloud_session cookie) is an OPAQUE
#     session token, not a Fly-metadata-friendly id like demo's session_id — resolving "which
#     Fly Machine does this token belong to" means asking the control-plane (POST /session/verify,
#     which already returns the account's `fly_machine_id`), not querying Fly's Machines API
#     directly. `FLY_MACHINE_ID` — this Machine's OWN id — is injected automatically by Fly on
#     every Machine, so "is this request mine?" is a plain string compare, no lookup needed for
#     the common case (only a MISROUTED request pays the control-plane round-trip).
#
# Deliberately NOT sharing code with demo_routing.py — same fly-replay TECHNIQUE, independently
# implemented, so a future change to one's semantics can never silently affect the other.
#
# A Machine that isn't an account Machine at all (ZAELAR_USER_ID unset — self-host, every demo
# Machine) never enters any of this — my_machine_id() below is only ever consulted when
# cloud_account.is_cloud_account() is True.
#
import asyncio
import os
import time

import httpx
from loguru import logger

SESSION_COOKIE = "zaelar_cloud_session"


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() not in ("", "0", "false", "no")


def is_account_routing_machine() -> bool:
    """True on any Machine that should PARTICIPATE in account routing — a real account Machine
    (ZAELAR_USER_ID set) OR the always-on base "router" (ZAELAR_ACCOUNT_ROUTER=1), mirroring
    demo_routing.py's ZAELAR_DEMO_ROUTER. Without the router flag, a request that lands on the base
    Machine (which has no account identity of its own) would just serve its OWN generic content
    instead of ever attempting a fly-replay — found live 2026-08-09 while testing Fase 2: the base
    Machine answered a cookie meant for a different account's Machine, silently, because nothing told
    it to even TRY routing."""
    from nucleo import cloud_account

    if cloud_account.is_cloud_account():
        return True
    return _truthy("ZAELAR_ACCOUNT_ROUTER")

# session_token -> (fly_machine_id, cached_at). A session token's owning Machine is STABLE for the
# token's lifetime (30 days) — same caching rationale as demo_routing.py's 502-wall fix.
_TOKEN_MACHINE_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 300.0

_INFLIGHT: dict[str, "asyncio.Future"] = {}


def my_machine_id() -> str | None:
    """This Machine's own Fly id — auto-injected by the Fly runtime, not something we set."""
    return (os.getenv("FLY_MACHINE_ID") or "").strip() or None


def _cache_get(token: str) -> str | None:
    hit = _TOKEN_MACHINE_CACHE.get(token)
    if hit and (time.monotonic() - hit[1]) < _CACHE_TTL:
        return hit[0]
    return None


def _cache_put(token: str, machine_id: str) -> None:
    _TOKEN_MACHINE_CACHE[token] = (machine_id, time.monotonic())


async def find_machine_for_session(
    session_token: str, *, control_plane_url: str, timeout: float = 3.0
) -> str | None:
    """Resolves a zaelar_cloud_session token to its account's fly_machine_id via the control-plane
    (POST /session/verify). Cached + single-flighted, same contract as
    demo_routing.find_machine_for_session. Fail-open: any error (network, no session, control-plane
    not configured) returns None — routing degrades to "serve locally", never a 500."""
    cached = _cache_get(session_token)
    if cached is not None:
        return cached

    inflight = _INFLIGHT.get(session_token)
    if inflight is not None:
        try:
            return await inflight
        except Exception:  # noqa: BLE001
            return None

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    _INFLIGHT[session_token] = fut
    try:
        mid = await _lookup_machine(session_token, control_plane_url=control_plane_url, timeout=timeout)
        if mid:
            _cache_put(session_token, mid)
        if not fut.done():
            fut.set_result(mid)
        return mid
    except Exception as e:  # noqa: BLE001
        logger.warning(f"account_routing: session lookup failed: {e}")
        if not fut.done():
            fut.set_result(None)
        return None
    finally:
        _INFLIGHT.pop(session_token, None)


async def _lookup_machine(session_token, *, control_plane_url, timeout) -> str | None:
    url = control_plane_url.rstrip("/") + "/session/verify"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.post(url, json={"session_token": session_token})
        res.raise_for_status()
        data = res.json()
    if not data.get("loggedIn"):
        return None
    machine = data.get("machine") or {}
    return machine.get("fly_machine_id")
