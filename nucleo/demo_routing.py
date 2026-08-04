#
# DEMO SESSION ROUTING (INI-018, added 2026-07-24) — fly-replay support for the cloud demo.
#
# Why this exists: cloud/infra/demo-session-worker/ gives every demo visitor their OWN Fly Machine
# (the engine is single-tenant-per-process, see engine/CLAUDE.md), but ALL demo Machines share one
# public hostname (`https://zaelar-demo.fly.dev`) — Fly's edge proxy picks whichever machine is
# available for a plain request, NOT necessarily the visitor's own one. With more than one demo
# session live at once, a visitor could silently land on a STRANGER's machine/session. Fly's
# documented fix for exactly this ("one machine per user") is the `fly-replay` response header:
# https://fly.io/docs/networking/dynamic-request-routing/ — whichever machine picks up a request
# first can tell Fly's proxy "actually, replay this on machine X" instead of serving it itself.
#
# This module is pure/testable logic + one Fly Machines API lookup call; the actual FastAPI
# middleware that calls it lives in server/__init__.py (`_demo_session_routing`).
#
# A machine that ISN'T a demo machine at all (ZAELAR_DEMO_SESSION unset — every self-host install
# and the operator's own cloud account) never enters any of this: `my_session_id()` returns None
# and the middleware no-ops on the very first check, zero cost.
#
import asyncio
import os
import time

import httpx
from loguru import logger

FLY_API_BASE = "https://api.machines.dev/v1"
SESSION_COOKIE = "zaelar_demo_session"
SESSION_QUERY_PARAM = "s"   # first landing on a fresh machine carries ?s=<id> (cookies don't cross
                            # from my.zaelar.com to zaelar-demo.fly.dev — different domains)

# session_id -> (machine_id, cached_at). A session's owning machine NEVER changes for its lifetime,
# so this can be cached hard. WHY THIS EXISTS (the 502-wall fix, 2026-08-04): the middleware
# (server/__init__.py) runs on EVERY request that lands on the "wrong" machine — and a browser
# loading the agent fires dozens of asset requests (dom.js, session.js, livekit-client, sse.js…),
# each Fly-load-balanced across all live machines. Without this cache, each one that missed the
# owning machine did a fresh `GET /machines` call to api.machines.dev; a page-load's worth of them
# hammered Fly's Machines API concurrently → rate-limited/timed-out (3s each) → a wall of 502s that
# killed the whole session ~20-30s in. Cached, the API is hit ~once per session per machine, and
# every subsequent replay is instant + API-free.
_SESSION_MACHINE_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 300.0   # seconds; generous — the mapping is stable, TTL is only a safety net for reaped/moved sessions


def _cache_get(session_id: str) -> str | None:
    hit = _SESSION_MACHINE_CACHE.get(session_id)
    if hit and (time.monotonic() - hit[1]) < _CACHE_TTL:
        return hit[0]
    return None


def _cache_put(session_id: str, machine_id: str) -> None:
    _SESSION_MACHINE_CACHE[session_id] = (machine_id, time.monotonic())


# SINGLE-FLIGHT: even with the cache, the FIRST burst of ~30 concurrent asset requests for a
# not-yet-cached session would each start their own Fly API call before any completes. This coalesces
# them: the first lookup in flight for a session owns a Future; every concurrent caller awaits it →
# exactly one API call, not N. Keyed per session_id.
_INFLIGHT: dict[str, "asyncio.Future"] = {}


# WARM POOL (2026-08-04) — a pool machine is pre-booted BLANK (engine fully warm, ~40s of boot
# already paid) and only learns WHICH session it serves at the first request. It carries
# ZAELAR_DEMO_POOL=1 (so it IS a demo machine — routing/energy/limits apply) but NO
# ZAELAR_DEMO_SESSION at boot; the first hit carrying ?s=<id> PINS it for the rest of its life. This
# preserves the single-tenant-per-process invariant (one machine still serves exactly one session)
# while killing the visitor-facing cold start: the boot happened before they arrived. The pin is a
# process-global set exactly once — a pool machine is used by ONE visitor then destroyed (never
# reused across visitors → zero cross-session contamination, same guarantee as a per-session machine).
_PINNED_SESSION: str | None = None


def _truthy(name: str) -> bool:
    return (os.getenv(name) or "").strip().lower() not in ("", "0", "false", "no")


def is_demo_machine() -> bool:
    """True on ANY cloud-demo Fly Machine that participates in session routing — a per-session
    machine (ZAELAR_DEMO_SESSION), a warm-pool machine (ZAELAR_DEMO_POOL=1, session learned at first
    touch), OR the always-on base machine in ROUTER mode (ZAELAR_DEMO_ROUTER=1: it fly-replays a
    session to its owning machine but never binds itself). False on every self-host install and the
    operator's own cloud account (none set) → routing/energy/limits all no-op there, exactly as before."""
    if (os.getenv("ZAELAR_DEMO_SESSION") or "").strip():
        return True
    return _truthy("ZAELAR_DEMO_POOL") or _truthy("ZAELAR_DEMO_ROUTER")


def _can_pin() -> bool:
    """Only a warm-POOL machine may bind itself to a session. The base router (ZAELAR_DEMO_ROUTER)
    routes but never serves a session as its own; a fixed per-session machine is already bound."""
    if (os.getenv("ZAELAR_DEMO_SESSION") or "").strip():
        return False
    return _truthy("ZAELAR_DEMO_POOL")


def pin_session(session_id: str) -> None:
    """Bind a warm-pool machine to a session, ONCE, at its first request. No-op on a per-session
    machine (immutable identity), on the base router (never binds), or if already pinned (first
    visitor wins; a stray later ?s= never re-binds a live machine)."""
    global _PINNED_SESSION
    if not _can_pin():
        return
    sid = (session_id or "").strip()
    if sid and _PINNED_SESSION is None:
        _PINNED_SESSION = sid
        logger.info(f"demo_routing: warm-pool machine pinned to session {sid}")


def my_session_id() -> str | None:
    """This Machine's OWN assigned session, or None if it isn't a demo machine (or is an as-yet
    unbound pool machine). A fixed ZAELAR_DEMO_SESSION wins; otherwise the pinned session (warm pool)."""
    v = (os.getenv("ZAELAR_DEMO_SESSION") or "").strip()
    if v:
        return v
    return _PINNED_SESSION


def requested_session_id(cookie_value: str | None, query_value: str | None) -> str | None:
    """Pure. Cookie wins once set (keeps a visitor pinned even if they still have the old ?s=...
    link bookmarked from before their session moved/expired); query param covers the FIRST hit."""
    v = (cookie_value or "").strip()
    if v:
        return v
    v = (query_value or "").strip()
    return v or None


async def find_machine_for_session(
    session_id: str, *, app_name: str, api_token: str, timeout: float = 3.0
) -> str | None:
    """Looks up which Machine in this Fly app owns `session_id` right now, via the
    `metadata.session_id` the Worker set at creation time (see
    cloud/infra/demo-session-worker/src/index.js::createFlyMachine). **Cached + single-flighted** so a
    page-load's worth of asset requests hit the Fly Machines API at most once per session, never once
    per request. Fail-open: any error (network, auth, malformed response) returns None rather than
    raising — routing degrades to "serve this request locally" (server/__init__.py), never a 500."""
    cached = _cache_get(session_id)
    if cached is not None:
        return cached

    inflight = _INFLIGHT.get(session_id)
    if inflight is not None:
        try:
            return await inflight
        except Exception:  # noqa: BLE001
            return None

    fut: asyncio.Future = asyncio.get_event_loop().create_future()
    _INFLIGHT[session_id] = fut
    try:
        mid = await _lookup_machine(session_id, app_name=app_name, api_token=api_token, timeout=timeout)
        if mid:
            _cache_put(session_id, mid)   # stable mapping — every later asset request skips the API
        if not fut.done():
            fut.set_result(mid)
        return mid
    except Exception as e:  # noqa: BLE001
        logger.warning(f"demo_routing: Fly machines lookup failed: {e}")
        if not fut.done():
            fut.set_result(None)
        return None
    finally:
        _INFLIGHT.pop(session_id, None)


async def _lookup_machine(session_id, *, app_name, api_token, timeout) -> str | None:
    """The raw Fly Machines API call — one GET, matched by metadata.session_id. Separated so
    find_machine_for_session() owns the cache/single-flight and this owns only the network."""
    url = f"{FLY_API_BASE}/apps/{app_name}/machines"
    async with httpx.AsyncClient(timeout=timeout) as client:
        res = await client.get(url, headers={"Authorization": f"Bearer {api_token}"})
        res.raise_for_status()
        machines = res.json()
    for m in machines or []:
        meta = ((m.get("config") or {}).get("metadata")) or {}
        if meta.get("session_id") == session_id:
            return m.get("id")
    return None
