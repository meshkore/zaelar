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
import os

import httpx
from loguru import logger

FLY_API_BASE = "https://api.machines.dev/v1"
SESSION_COOKIE = "zaelar_demo_session"
SESSION_QUERY_PARAM = "s"   # first landing on a fresh machine carries ?s=<id> (cookies don't cross
                            # from my.zaelar.com to zaelar-demo.fly.dev — different domains)


def my_session_id() -> str | None:
    """This Machine's OWN assigned session (set by the Worker at creation time), or None if this
    isn't a demo machine at all."""
    v = (os.getenv("ZAELAR_DEMO_SESSION") or "").strip()
    return v or None


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
    cloud/infra/demo-session-worker/src/index.js::createFlyMachine). Fail-open: any error (network,
    auth, malformed response) returns None rather than raising — routing degrades to "serve this
    request locally" (server/__init__.py), never a 500."""
    url = f"{FLY_API_BASE}/apps/{app_name}/machines"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            res = await client.get(url, headers={"Authorization": f"Bearer {api_token}"})
            res.raise_for_status()
            machines = res.json()
    except Exception as e:  # noqa: BLE001
        logger.warning(f"demo_routing: Fly machines lookup failed: {e}")
        return None

    for m in machines or []:
        meta = ((m.get("config") or {}).get("metadata")) or {}
        if meta.get("session_id") == session_id:
            return m.get("id")
    return None
